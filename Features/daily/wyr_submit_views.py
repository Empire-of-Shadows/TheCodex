"""
Member question submissions - the screens a member and a moderator each see.

Two surfaces:

  * ``SubmissionBuilderView`` - the member's ephemeral draft. Author-locked and
    short-lived. It only ever offers the formats the server actually posts, so
    a member cannot spend effort on a question that would never run.
  * ``SubmissionReviewView`` - the persistent Approve / Reject post in the review
    channel. ``timeout=None`` with static custom_ids, registered once at startup,
    because a review post routinely outlives a restart. A view rebuilt that way
    carries no submission id, so the handlers recover it from the message.

The reject reason modal is here too; approving needs no extra input beyond the
age-restriction toggle the reviewer already sees.
"""

from __future__ import annotations

from typing import Awaitable, Callable, List, Optional

import discord

from storage.log import get_logger

from Features.daily.wyr_bank import FORMAT_LABELS, question_options
from Features.daily.wyr_question_form import FORMAT_EMOJI, QuestionFormModal

logger = get_logger("WYRSubmitViews")

APPROVE_BUTTON_ID = "wyr:sub:approve"
REJECT_BUTTON_ID = "wyr:sub:reject"
NSFW_BUTTON_ID = "wyr:sub:nsfw"

#: How long a member's draft stays open before it is abandoned.
_BUILDER_TIMEOUT = 600


def build_review_embed(submission: dict, *, guild: discord.Guild = None,
                       decided_by: discord.abc.User = None,
                       outcome: str = "", reason: str = "",
                       question_id: int = None,
                       format_warning: str = "") -> discord.Embed:
    """The review post for one submission, before and after a decision."""
    fmt = submission.get("format") or "wyr"
    colour = {
        "approved": discord.Color.green(),
        "rejected": discord.Color.red(),
    }.get(outcome, discord.Color.blurple())

    embed = discord.Embed(
        title=f"{FORMAT_EMOJI.get(fmt, '•')} Question suggestion",
        description=submission.get("original", ""),
        color=colour,
    )

    options = question_options(submission)
    if options:
        embed.add_field(
            name="Answers",
            value="\n".join(f"{n}. {text}" for n, text in options),
            inline=False,
        )

    embed.add_field(name="Type", value=FORMAT_LABELS.get(fmt, fmt), inline=True)
    embed.add_field(
        name="Suggested by",
        value=f"<@{submission.get('user_id')}>",
        inline=True,
    )
    if submission.get("tags"):
        embed.add_field(name="Tags", value=", ".join(submission["tags"]), inline=True)

    # The reviewer needs to know BEFORE approving that this type is switched
    # off, not discover it days later when the question never appears.
    if format_warning and not outcome:
        embed.add_field(name="Heads up", value=format_warning, inline=False)

    if outcome == "approved":
        note = f"✅ Approved by {decided_by.mention if decided_by else 'a moderator'}"
        if question_id is not None:
            note += f" - added as question **#{question_id}**"
        embed.add_field(name="Decision", value=note, inline=False)
    elif outcome == "rejected":
        note = f"❌ Declined by {decided_by.mention if decided_by else 'a moderator'}"
        if reason:
            note += f"\n> {reason}"
        embed.add_field(name="Decision", value=note, inline=False)

    embed.set_footer(text=f"Suggestion {str(submission.get('submission_id', ''))[:8]}")
    return embed


def build_decision_dm_embed(submission: dict, *, guild_name: str, approved: bool,
                            reason: str = "") -> discord.Embed:
    """What the member is told about their own suggestion."""
    if approved:
        return discord.Embed(
            title="✅ Your question was approved",
            description=(
                f"Your question is now in **{guild_name}**'s daily rotation:\n\n"
                f"> {submission.get('original', '')}"
            ),
            color=discord.Color.green(),
        )
    embed = discord.Embed(
        title="Your question was not added",
        description=(
            f"A moderator in **{guild_name}** did not add this one:\n\n"
            f"> {submission.get('original', '')}"
        ),
        color=discord.Color.light_grey(),
    )
    if reason:
        embed.add_field(name="Reason given", value=reason, inline=False)
    embed.set_footer(text="Feel free to suggest another.")
    return embed


class RejectReasonModal(discord.ui.Modal, title="Decline this suggestion"):
    """Optional reason, passed on to the member who suggested it."""

    reason_input = discord.ui.TextInput(
        label="Reason (optional)",
        placeholder="Shown to the member who suggested it.",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, callback: Callable[[discord.Interaction, str], Awaitable[None]]):
        super().__init__()
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, (self.reason_input.value or "").strip())


class SubmissionReviewView(discord.ui.View):
    """Persistent Approve / Reject / age-restrict buttons on a review post.

    Registered once at startup with no submission id. Every handler resolves the
    submission from ``interaction.message.id`` when it has none of its own, which
    is what keeps buttons working on posts made before the last restart.
    """

    def __init__(self, submission_id: str = None, *, nsfw: bool = False):
        super().__init__(timeout=None)
        self.submission_id = submission_id
        self.nsfw = nsfw

    def _cog(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("WYR")
        if not cog:
            raise RuntimeError("WYR cog not available")
        return cog

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success,
                       emoji="✅", custom_id=APPROVE_BUTTON_ID)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cog(interaction).handle_submission_approve(interaction, self)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger,
                       emoji="❌", custom_id=REJECT_BUTTON_ID)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cog(interaction).handle_submission_reject(interaction, self)

    @discord.ui.button(label="Age-restrict", style=discord.ButtonStyle.secondary,
                       emoji="🔞", custom_id=NSFW_BUTTON_ID)
    async def toggle_nsfw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark the question age-restricted before approving it.

        Only a reviewer can set this. A member never can: the review post itself
        renders in a channel that may not be age-restricted, so a submission
        always arrives marked safe.
        """
        await self._cog(interaction).handle_submission_nsfw_toggle(interaction, self)


class SubmissionBuilderView(discord.ui.LayoutView):
    """A member's ephemeral draft of one question.

    Author-locked, because it is sent ephemerally but Discord still routes
    component clicks by message rather than by viewer.
    """

    def __init__(self, *, member_id: int, formats: List[str],
                 on_submit: Callable[[discord.Interaction, str, str, List[str], List[str]],
                                     Awaitable[None]]):
        super().__init__(timeout=_BUILDER_TIMEOUT)
        self.member_id = member_id
        self.formats = formats
        self._on_submit = on_submit

        self.draft_format: Optional[str] = formats[0] if len(formats) == 1 else None
        self.draft_text: str = ""
        self.draft_options: List[str] = []
        self.draft_tags: List[str] = []

        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member_id:
            await interaction.response.send_message(
                "That suggestion box belongs to someone else. Run `/wyr submit` to "
                "start your own.",
                ephemeral=True,
            )
            return False
        return True

    # -- rendering --------------------------------------------------------

    def _summary(self) -> str:
        if not self.draft_format:
            return "**1.** Pick what kind of question you want to suggest."
        label = FORMAT_LABELS.get(self.draft_format, self.draft_format)
        lines = [f"**Type:** {FORMAT_EMOJI.get(self.draft_format, '')} {label}"]
        if not self.draft_text:
            lines.append("\n**2.** Now write it, using the button below.")
            return "\n".join(lines)
        lines.append(f"\n> {self.draft_text}")
        for index, option in enumerate(self.draft_options, start=1):
            lines.append(f"{index}. {option}")
        if self.draft_tags:
            lines.append(f"\n*Tags: {', '.join(self.draft_tags)}*")
        lines.append("\n**3.** Send it for a moderator to look at.")
        return "\n".join(lines)

    def _render(self) -> None:
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(
            "## Suggest a question\n"
            "If a moderator approves it, it joins this server's daily rotation."
        ))
        container.add_item(discord.ui.TextDisplay(self._summary()))

        if len(self.formats) > 1:
            select = discord.ui.Select(
                placeholder="What kind of question?",
                options=[
                    discord.SelectOption(
                        label=FORMAT_LABELS.get(f, f),
                        value=f,
                        emoji=FORMAT_EMOJI.get(f),
                        default=(f == self.draft_format),
                    )
                    for f in self.formats
                ],
                min_values=1,
                max_values=1,
            )
            select.callback = self._on_pick_format
            container.add_item(discord.ui.ActionRow(select))

        row = discord.ui.ActionRow()
        write = discord.ui.Button(
            label="Write it" if not self.draft_text else "Edit it",
            style=discord.ButtonStyle.primary,
            disabled=self.draft_format is None,
        )
        write.callback = self._on_write
        row.add_item(write)

        send = discord.ui.Button(
            label="Send for review",
            style=discord.ButtonStyle.success,
            disabled=not self.draft_text,
        )
        send.callback = self._on_send
        row.add_item(send)

        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self._on_cancel
        row.add_item(cancel)
        container.add_item(row)

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self._render()
        await interaction.response.edit_message(view=self)

    # -- handlers ---------------------------------------------------------

    async def _on_pick_format(self, interaction: discord.Interaction) -> None:
        chosen = interaction.data.get("values", [None])[0]
        if chosen != self.draft_format:
            # The answers belong to the old format's rules, so they are dropped
            # rather than silently carried into a format that would reject them.
            self.draft_options = []
        self.draft_format = chosen
        await self._refresh(interaction)

    async def _on_write(self, interaction: discord.Interaction) -> None:
        modal = QuestionFormModal(
            self.draft_format,
            self._on_form_submit,
            title="Suggest a question",
        )
        modal.question_input.default = self.draft_text or None
        if modal.options_input is not None and self.draft_options:
            modal.options_input.default = "\n".join(self.draft_options)
        if self.draft_tags:
            modal.tags_input.default = ", ".join(self.draft_tags)
        await interaction.response.send_modal(modal)

    async def _on_form_submit(self, interaction: discord.Interaction, text, options, tags) -> None:
        self.draft_text = text
        self.draft_options = options
        self.draft_tags = tags
        await self._refresh(interaction)

    async def _on_send(self, interaction: discord.Interaction) -> None:
        await self._on_submit(
            interaction, self.draft_format, self.draft_text,
            self.draft_options, self.draft_tags,
        )

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(
            "Suggestion discarded. Nothing was sent."
        ))
        view.add_item(container)
        await interaction.response.edit_message(view=view)
        self.stop()
