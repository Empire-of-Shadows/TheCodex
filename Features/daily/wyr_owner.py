"""
`/wyrbank` - the bot owner's view of the whole question bank.

Servers fill their own private banks. This is where the best of those get
promoted into the shared bank every server draws from, and where questions are
added to that shared bank in the first place.

A slash command group rather than an admin-panel node or a dashboard page, and
the reason is worth writing down. The panel's authorization resolves a role FOR
A GUILD (``admin`` or ``none``) and has no concept of the bot owner; the
dashboard's is per-guild Manage Server. Giving either an owner tier means
editing a shared engine master, which re-vendors into six bots and has to be
proved not to have moved any of their panels - an enormous blast radius for a
tool with exactly one user. ``bot.is_owner`` costs one file.

The group is registered to a single guild when ``OWNER_GUILD_ID`` is set, so it
never shows up in anyone else's command list. That is tidiness; the ownership
check is the actual gate.
"""

from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from storage.log import get_logger

from Features.daily.wyr_bank import (
    FORMAT_LABELS,
    FORMATS,
    question_options,
    validate_question,
    wyr_bank,
)
from Features.daily.wyr_question_form import FORMAT_EMOJI, QuestionFormModal

logger = get_logger("WYRBankOwner")

_PAGE_SIZE = 5


def _is_bot_owner():
    """Allow only the bot's owner. The real gate, whatever the command scoping."""
    async def predicate(interaction: discord.Interaction) -> bool:
        return await interaction.client.is_owner(interaction.user)
    return app_commands.check(predicate)


def _describe(question: dict) -> str:
    fmt = question.get("format") or "wyr"
    text = question.get("original", "")
    if len(text) > 160:
        text = text[:157] + "..."
    lines = [f"{FORMAT_EMOJI.get(fmt, '•')} **#{question.get('id')}** {text}"]
    options = question_options(question)
    if options:
        lines.append("  " + " · ".join(f"{n}. {v}" for n, v in options))
    origin = question.get("guild_id") or question.get("origin_guild_id")
    meta = [f"guild `{origin}`" if origin else "shared"]
    if question.get("nsfw"):
        meta.append("age-restricted")
    if question.get("source"):
        meta.append(str(question["source"]))
    lines.append("  *" + " · ".join(meta) + "*")
    return "\n".join(lines)


class _ReviewView(discord.ui.View):
    """Page through guild-owned questions, promoting or deleting one at a time."""

    def __init__(self, owner_id: int, questions: list):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.questions = questions
        self.page = 0
        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @property
    def _page_items(self) -> list:
        start = self.page * _PAGE_SIZE
        return self.questions[start:start + _PAGE_SIZE]

    def _render(self) -> None:
        self.clear_items()
        items = self._page_items
        if not items:
            return

        select = discord.ui.Select(
            placeholder="Pick a question to act on...",
            options=[
                discord.SelectOption(
                    label=f"#{q['id']} {str(q.get('original',''))}"[:100],
                    value=str(q["id"]),
                    description=(FORMAT_LABELS.get(q.get("format") or "wyr"))[:100],
                )
                for q in items
            ],
            min_values=1, max_values=1,
        )
        select.callback = self._on_pick
        self.add_item(select)

        prev_button = discord.ui.Button(
            label="Previous", style=discord.ButtonStyle.secondary, disabled=self.page == 0
        )
        prev_button.callback = self._on_prev
        self.add_item(prev_button)

        last_page = max(0, (len(self.questions) - 1) // _PAGE_SIZE)
        next_button = discord.ui.Button(
            label="Next", style=discord.ButtonStyle.secondary,
            disabled=self.page >= last_page,
        )
        next_button.callback = self._on_next
        self.add_item(next_button)

    def embed(self) -> discord.Embed:
        last_page = max(0, (len(self.questions) - 1) // _PAGE_SIZE)
        embed = discord.Embed(
            title="Guild-owned questions",
            description="\n\n".join(_describe(q) for q in self._page_items)
                        or "Nothing here.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"Page {self.page + 1} of {last_page + 1} · "
                 f"{len(self.questions)} question(s)"
        )
        return embed

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self._render()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        await self._refresh(interaction)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self.page += 1
        await self._refresh(interaction)

    async def _on_pick(self, interaction: discord.Interaction) -> None:
        number = int(interaction.data["values"][0])
        question = next((q for q in self.questions if q.get("id") == number), None)
        if question is None:
            await interaction.response.send_message(
                "That one is no longer in the list.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Promote or delete",
                description=_describe(question),
                color=discord.Color.orange(),
            ),
            view=_DecisionView(self, question),
        )


class _DecisionView(discord.ui.View):
    """Confirm what happens to one question."""

    def __init__(self, parent: _ReviewView, question: dict):
        super().__init__(timeout=300)
        self.parent = parent
        self.question = question

        promote = discord.ui.Button(label="Promote to shared bank",
                                    style=discord.ButtonStyle.success, emoji="⬆️")
        promote.callback = self._on_promote
        self.add_item(promote)

        delete = discord.ui.Button(label="Delete", style=discord.ButtonStyle.danger,
                                   emoji="🗑️")
        delete.callback = self._on_delete
        self.add_item(delete)

        back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
        back.callback = self._on_back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.parent.owner_id

    def _drop_from_parent(self) -> None:
        self.parent.questions = [
            q for q in self.parent.questions if q["id"] != self.question["id"]
        ]
        last_page = max(0, (len(self.parent.questions) - 1) // _PAGE_SIZE)
        self.parent.page = min(self.parent.page, last_page)

    async def _on_promote(self, interaction: discord.Interaction) -> None:
        fmt = self.question.get("format") or "wyr"
        if fmt != "wyr":
            # Promoting a non-Would-You-Rather makes it available to every
            # server on that type, so the blast radius gets named out loud.
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Confirm - this is not a Would You Rather",
                    description=(
                        f"{_describe(self.question)}\n\n"
                        f"Promoting this puts a **{FORMAT_LABELS.get(fmt, fmt)}** into "
                        f"the shared bank. Every server that posts that type will "
                        f"start seeing it."
                    ),
                    color=discord.Color.red(),
                ),
                view=_ConfirmPromoteView(self),
            )
            return
        await self._do_promote(interaction)

    async def _do_promote(self, interaction: discord.Interaction) -> None:
        ok = await wyr_bank.promote_to_global(self.question["id"], interaction.user.id)
        self._drop_from_parent()
        self.parent._render()
        await interaction.response.edit_message(
            embed=self.parent.embed(), view=self.parent
        )
        await interaction.followup.send(
            f"{'✅ Promoted' if ok else '❌ Could not promote'} question "
            f"**#{self.question['id']}**.",
            ephemeral=True,
        )

    async def _on_delete(self, interaction: discord.Interaction) -> None:
        guild_id = self.question.get("guild_id")
        ok = await wyr_bank.delete_question(self.question["_id"], guild_id)
        self._drop_from_parent()
        self.parent._render()
        await interaction.response.edit_message(
            embed=self.parent.embed(), view=self.parent
        )
        await interaction.followup.send(
            f"{'🗑️ Deleted' if ok else '❌ Could not delete'} question "
            f"**#{self.question['id']}**.",
            ephemeral=True,
        )

    async def _on_back(self, interaction: discord.Interaction) -> None:
        self.parent._render()
        await interaction.response.edit_message(
            embed=self.parent.embed(), view=self.parent
        )


class _ConfirmPromoteView(discord.ui.View):
    def __init__(self, decision: _DecisionView):
        super().__init__(timeout=120)
        self.decision = decision

        confirm = discord.ui.Button(label="Promote anyway",
                                    style=discord.ButtonStyle.danger)
        confirm.callback = self._on_confirm
        self.add_item(confirm)

        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self._on_cancel
        self.add_item(cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.decision.parent.owner_id

    async def _on_confirm(self, interaction: discord.Interaction) -> None:
        await self.decision._do_promote(interaction)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        await self.decision._on_back(interaction)


class WYRBankGroup(app_commands.Group):
    """Owner-only tools over the whole question bank."""

    def __init__(self):
        super().__init__(
            name="wyrbank",
            description="Question bank tools (bot owner only)",
            guild_only=True,
        )

    @app_commands.command(name="review",
                          description="Review guild-owned questions and promote the good ones")
    @app_commands.describe(guild_id="Only show one server's questions")
    @_is_bot_owner()
    async def review(self, interaction: discord.Interaction, guild_id: str = None):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(guild_id) if guild_id else None
        except (TypeError, ValueError):
            await interaction.followup.send("That is not a server ID.", ephemeral=True)
            return

        if target is not None:
            questions = await wyr_bank.list_questions(target, owned_only=True, limit=500)
        else:
            questions = await wyr_bank._col.find_many(
                {"scope": "guild"}, sort=[("id", -1)], limit=500
            )

        if not questions:
            await interaction.followup.send(
                "No guild-owned questions to review.", ephemeral=True
            )
            return

        view = _ReviewView(interaction.user.id, questions)
        await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="add",
                          description="Add a question to the shared bank every server draws from")
    @app_commands.describe(question_type="Which kind of question to add")
    @app_commands.choices(question_type=[
        app_commands.Choice(name=FORMAT_LABELS[f], value=f) for f in FORMATS
    ])
    @_is_bot_owner()
    async def add(self, interaction: discord.Interaction,
                  question_type: app_commands.Choice[str], nsfw: bool = False):
        async def _on_submit(modal_interaction, text, options, tags):
            ok, cleaned, error = validate_question(question_type.value, text, options, tags)
            if not ok:
                await modal_interaction.response.send_message(f"❌ {error}", ephemeral=True)
                return

            from Features.daily.wyr_bank import normalize_text_key
            text_key = normalize_text_key(
                cleaned["format"], cleaned["original"],
                [v for _, v in question_options(cleaned)],
            )
            existing = await wyr_bank.find_duplicate(text_key, None)
            if existing:
                await modal_interaction.response.send_message(
                    f"The shared bank already has that, as **#{existing['id']}**.",
                    ephemeral=True,
                )
                return

            # guild_id=None means scope "global" - the shared bank.
            question = await wyr_bank.insert_question(
                cleaned, guild_id=None, source="owner", nsfw=nsfw
            )
            if not question:
                await modal_interaction.response.send_message(
                    "❌ Could not add that question.", ephemeral=True
                )
                return
            await modal_interaction.response.send_message(
                f"✅ Added to the shared bank as **#{question['id']}**"
                f"{' (age-restricted)' if nsfw else ''}.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            QuestionFormModal(question_type.value, _on_submit,
                              title="Add to the shared bank")
        )

    @app_commands.command(name="stats", description="Question bank totals")
    @_is_bot_owner()
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        rows = await wyr_bank._col.aggregate([
            {"$group": {
                "_id": {"scope": {"$ifNull": ["$scope", "global"]},
                        "format": {"$ifNull": ["$format", "wyr"]}},
                "count": {"$sum": 1},
            }},
        ])
        shared = {f: 0 for f in FORMATS}
        private = {f: 0 for f in FORMATS}
        for row in rows:
            bucket = shared if row["_id"]["scope"] == "global" else private
            fmt = row["_id"]["format"]
            if fmt in bucket:
                bucket[fmt] += int(row["count"])

        top = await wyr_bank._col.aggregate([
            {"$match": {"scope": "guild"}},
            {"$group": {"_id": "$guild_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ])

        embed = discord.Embed(title="Question bank", color=discord.Color.blurple())
        embed.add_field(
            name=f"Shared bank ({sum(shared.values())})",
            value="\n".join(f"{FORMAT_LABELS[f]}: {n}" for f, n in shared.items()) or "empty",
            inline=True,
        )
        embed.add_field(
            name=f"Guild-owned ({sum(private.values())})",
            value="\n".join(f"{FORMAT_LABELS[f]}: {n}" for f, n in private.items()) or "empty",
            inline=True,
        )
        if top:
            embed.add_field(
                name="Servers with their own questions",
                value="\n".join(f"`{r['_id']}` - {r['count']}" for r in top),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


class WYRBankOwner(commands.Cog):
    """Registers the owner-only `/wyrbank` group."""

    def __init__(self, bot):
        self.bot = bot
        self.group = WYRBankGroup()

        # Scoped to the home guild when one is configured, so it never appears
        # in another server's command list. Without the variable it registers
        # globally and the ownership check alone keeps it private.
        owner_guild = os.getenv("OWNER_GUILD_ID")
        if owner_guild:
            try:
                bot.tree.add_command(self.group, guild=discord.Object(id=int(owner_guild)))
                logger.info(f"/wyrbank registered to guild {owner_guild}")
                return
            except (TypeError, ValueError):
                logger.warning(
                    f"OWNER_GUILD_ID is not a server ID ({owner_guild!r}); "
                    f"registering /wyrbank globally instead"
                )
        bot.tree.add_command(self.group)

    async def cog_unload(self):
        owner_guild = os.getenv("OWNER_GUILD_ID")
        try:
            if owner_guild:
                self.bot.tree.remove_command(
                    "wyrbank", guild=discord.Object(id=int(owner_guild))
                )
            else:
                self.bot.tree.remove_command("wyrbank")
        except (TypeError, ValueError):
            self.bot.tree.remove_command("wyrbank")


async def setup(bot):
    await bot.add_cog(WYRBankOwner(bot))
