import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, cast
import uuid
import os
from dotenv import load_dotenv

from storage.log import get_logger, log_context, PerformanceLogger
from storage.settings.config_manager import get_config
from storage.settings.collections import db_manager
from admin.setup_notice import send_setup_notice

logger = get_logger("Suggestion")

load_dotenv()

# Categories offered in both the slash-command choices and the interactive builder.
SUGGESTION_CATEGORIES = [
    "Bot Feature",
    "Server Improvement",
    "Event Idea",
    "Rule Change",
    "Other",
]

# Statuses a suggestion can carry, in the order they are offered as filters.
SUGGESTION_STATUSES = [
    "Pending",
    "Under Review",
    "Approved",
    "Implemented",
    "Rejected",
    "On Hold",
]

# Filter option sets for the browser view. They mirror the /suggestions slash
# command choices exactly, "All" included, so a filter picked on the command and
# the same filter picked in the view mean the same thing.
BROWSE_CATEGORY_OPTIONS = ["All"] + SUGGESTION_CATEGORIES
BROWSE_STATUS_OPTIONS = ["All"] + SUGGESTION_STATUSES

#: What an opted-out member is told when their vote is not saved.
OPTED_OUT_VOTE_NOTICE = (
    "Your vote was not recorded. You have turned off data collection, so votes "
    "cannot be saved against your account. You can turn it back on any time on "
    "the privacy page of the dashboard."
)


async def write_anonymous_author_audit(*, guild_id, suggestion_id: str, author) -> bool:
    """Record who wrote a forced-anonymous suggestion, for staff to look up.

    The admin-channel copy deliberately does NOT name an opted-out member - the
    privacy page promises no record tied to them in the places other people
    read. Moderation still has to be possible, so the link lives here instead:
    one audit entry, findable by Suggestion ID, that an admin has to go looking
    for rather than one that sits in a channel.

    Best-effort by design (the engine ``AuditLog.log`` swallows its own errors
    and returns False); the suggestion is already posted by the time this runs.
    """
    from admin.settings.bindings import _get_audit_log

    return await _get_audit_log().log(
        guild_id=str(guild_id),
        actor_id=str(author.id),
        actor_name=str(author),
        section="suggestions",
        key="anonymous_author",
        entity_id=suggestion_id,
        note=(
            "Author of an anonymous suggestion. Withheld from the admin channel "
            "because this member has turned off data collection."
        ),
    )


async def _opted_out(client, user_id) -> bool:
    """Whether this member has turned off data collection for suggestions.

    Fails OPEN. If the preference cache never attached (its startup wiring
    failed), suggestions behave exactly as they did before the opt-out existed
    rather than every submission silently turning anonymous. ``is_opted_out``
    already folds in the "all" master switch.

    The id is coerced to ``str`` here, in the bot's own seam: the preference
    document stores it as a string like every other snowflake in codex, and the
    engine cache queries with the id exactly as handed over, so an int would
    match nothing and read as "not opted out".
    """
    prefs = getattr(client, "privacy_prefs", None)
    if prefs is None:
        return False
    try:
        return await prefs.is_opted_out(str(user_id), "suggestions")
    except Exception as e:
        logger.error(
            f"Could not read privacy preferences for {user_id}: {e}", exc_info=True
        )
        return False


class SuggestionView(discord.ui.View):
    def __init__(self, suggestion_id: str, db_manager):
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id
        self.db_manager = db_manager

    @discord.ui.button(label="👍", style=cast(discord.ButtonStyle, discord.ButtonStyle.success), custom_id="upvote")
    async def upvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Upvote button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "upvote")

    @discord.ui.button(label="👎", style=cast(discord.ButtonStyle, discord.ButtonStyle.danger), custom_id="downvote")
    async def downvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Downvote button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "downvote")

    @discord.ui.button(label="❤️", style=cast(discord.ButtonStyle, discord.ButtonStyle.primary), custom_id="love")
    async def love(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Love button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "love")

    @discord.ui.button(label="🤔", style=cast(discord.ButtonStyle, discord.ButtonStyle.secondary), custom_id="thinking")
    async def thinking(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Thinking button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "thinking")

    async def _handle_vote(self, interaction: discord.Interaction, vote_type: str):
        with PerformanceLogger(logger, f"handle_vote_{vote_type}"):
            user_id = interaction.user.id

            # A vote is stored against the voter's id, so there is no way to
            # count one for a member who has turned data collection off. Nothing
            # is written: no vote row, no tally change, no user stats.
            if await _opted_out(interaction.client, user_id):
                logger.info(
                    f"Vote from user {user_id} not recorded: data collection is "
                    f"turned off for this member"
                )
                await interaction.response.send_message(
                    OPTED_OUT_VOTE_NOTICE, ephemeral=True
                )
                return

            # The persistent view registered on startup carries no suggestion_id,
            # so after a restart recover it from the message the buttons are on.
            suggestion_id = self.suggestion_id
            if not suggestion_id:
                suggestion_id = await self.db_manager.get_suggestion_id_from_message(
                    interaction.message.id
                )
            if not suggestion_id:
                logger.warning(
                    f"Could not resolve suggestion for {vote_type} vote from user "
                    f"{user_id} on message {interaction.message.id}"
                )
                await interaction.response.send_message(
                    "❌ Could not determine which suggestion you're voting on.",
                    ephemeral=True,
                )
                return

            logger.info(f"Processing {vote_type} vote from user {user_id} for suggestion {suggestion_id}")

            try:
                result = await self.db_manager.add_vote(suggestion_id, user_id, vote_type)

                if result["success"]:
                    logger.info(f"Vote processed successfully: {result['message']}")
                    vote_counts = await self.db_manager.get_vote_counts(suggestion_id)
                    embed = interaction.message.embeds[0] if interaction.message.embeds else None

                    if embed:
                        # Update vote counts in embed
                        vote_display = f"👍 {vote_counts.get('upvote', 0)} | 👎 {vote_counts.get('downvote', 0)} | ❤️ {vote_counts.get('love', 0)} | 🤔 {vote_counts.get('thinking', 0)}"

                        # Update or add vote field
                        for i, field in enumerate(embed.fields):
                            if field.name == "Votes":
                                embed.set_field_at(i, name="Votes", value=vote_display, inline=False)
                                break
                        else:
                            embed.add_field(name="Votes", value=vote_display, inline=False)

                        await interaction.response.edit_message(embed=embed, view=self)
                        logger.debug(f"Updated embed with new vote counts: {vote_display}")
                    else:
                        await interaction.response.send_message(f"✅ {result['message']}", ephemeral=True)
                else:
                    logger.warning(f"Vote processing failed: {result['message']}")
                    await interaction.response.send_message(f"❌ {result['message']}", ephemeral=True)

            except Exception as e:
                logger.error(f"Error handling vote: {e}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing your vote.",
                                                            ephemeral=True)


class SuggestionModal(discord.ui.Modal):
    def __init__(self, template_type: str, anonymous: bool = False):
        super().__init__(title=f"{template_type} Suggestion")
        self.template_type = template_type
        self.anonymous = anonymous
        logger.debug(f"SuggestionModal initialized for template type: {template_type}")

        templates = {
            "Bot Feature": {
                "title": "Feature Request",
                "description": "Describe the bot feature you'd like to see",
                "use_case": "How would this feature be used?",
                "priority": "How important is this feature? (1-10)"
            },
            "Server Rule": {
                "title": "Rule Suggestion",
                "description": "What rule change would you like to propose?",
                "use_case": "Why is this rule needed?",
                "priority": "How urgent is this change? (1-10)"
            },
            "Event Proposal": {
                "title": "Event Idea",
                "description": "Describe the event you'd like to organize",
                "use_case": "When should this event happen?",
                "priority": "How much interest do you think this will generate? (1-10)"
            },
            "Channel Request": {
                "title": "Channel Request",
                "description": "What type of channel would you like added?",
                "use_case": "What would this channel be used for?",
                "priority": "How needed is this channel? (1-10)"
            }
        }

        template = templates.get(template_type, templates["Bot Feature"])

        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder=template["title"],
            max_length=100
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder=template["description"],
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.use_case_input = discord.ui.TextInput(
            label="Use Case/Reasoning",
            placeholder=template["use_case"],
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.priority_input = discord.ui.TextInput(
            label="Priority",
            placeholder=template["priority"],
            max_length=2
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.use_case_input)
        self.add_item(self.priority_input)

    async def on_submit(self, interaction: discord.Interaction):
        with log_context(logger, f"template_submission_{self.template_type}"):
            # Combine all inputs into suggestion text
            suggestion_text = f"**{self.title_input.value}**\n\n{self.description_input.value}\n\n**Use Case:** {self.use_case_input.value}\n\n**Priority:** {self.priority_input.value}"

            logger.info(
                f"Template suggestion submitted by user {interaction.user.id} - Type: {self.template_type}, Length: {len(suggestion_text)} chars")

            # Get the suggestion cog and call its suggest method
            cog = interaction.client.get_cog("SuggestionCog")
            if cog:
                await cog._process_suggestion(interaction, suggestion_text, self.anonymous, self.template_type)
            else:
                logger.error("SuggestionCog not found when processing template submission")
                await interaction.response.send_message("❌ System error: Suggestion service unavailable.",
                                                        ephemeral=True)


class SuggestionBuilderModal(discord.ui.Modal):
    """Text-field editor for the interactive builder.

    Opened from the builder's Edit button. On submit it writes the values
    back onto the parent builder view and re-renders the builder message.
    """

    def __init__(self, builder: "SuggestionBuilderView"):
        super().__init__(title="Suggestion Details")
        self.builder = builder

        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="A short headline for your suggestion",
            default=builder.draft_title or None,
            max_length=100,
            required=True,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Describe your suggestion in detail",
            style=discord.TextStyle.paragraph,
            default=builder.draft_description or None,
            max_length=1000,
            required=True,
        )
        self.details_input = discord.ui.TextInput(
            label="Additional Details (optional)",
            placeholder="Reasoning, use case, timing, anything extra",
            style=discord.TextStyle.paragraph,
            default=builder.draft_details or None,
            max_length=500,
            required=False,
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.details_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder.draft_title = self.title_input.value.strip()
        self.builder.draft_description = self.description_input.value.strip()
        self.builder.draft_details = self.details_input.value.strip()
        logger.debug(
            f"Builder draft updated by user {interaction.user.id} - title set: {bool(self.builder.draft_title)}")
        self.builder.render()
        await interaction.response.edit_message(view=self.builder)


class SuggestionBuilderView(discord.ui.LayoutView):
    """Interactive Components v2 builder for composing a suggestion.

    Shown when /suggest is run without options. Holds the in-progress draft
    on the instance (ephemeral, author-locked, short-lived). A single Edit
    button opens a modal for the text fields; a select picks the category and
    a toggle button flips anonymity; Submit hands off to the cog's normal
    processing path.
    """

    def __init__(
        self,
        cog: "SuggestionCog",
        author_id: int,
        initial_category: str = "Other",
        initial_anonymous: bool = False,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.category = initial_category if initial_category in SUGGESTION_CATEGORIES else "Other"
        self.anonymous = initial_anonymous
        self.draft_title = ""
        self.draft_description = ""
        self.draft_details = ""
        self.render()

    # ---- state -> text -------------------------------------------------

    def _summary_text(self) -> str:
        title = self.draft_title or "*not set*"
        description = self.draft_description or "*not set*"
        details = self.draft_details or "*none*"
        anon = "On" if self.anonymous else "Off"
        return (
            "## New Suggestion\n"
            f"**Title:** {title}\n"
            f"**Description:** {description}\n"
            f"**Details:** {details}\n"
            f"**Category:** {self.category}\n"
            f"**Anonymous:** {anon}\n\n"
            "Use **Edit Details** to fill in your suggestion, pick a category, "
            "toggle anonymity, then press **Submit**."
        )

    def _compose_text(self) -> str:
        parts = [f"**{self.draft_title}**", "", self.draft_description]
        if self.draft_details:
            parts.extend(["", f"**Details:** {self.draft_details}"])
        return "\n".join(parts)

    # ---- rendering -----------------------------------------------------

    def render(self):
        """Rebuild the layout to reflect current draft state."""
        self.clear_items()

        container = discord.ui.Container(accent_color=0x5865F2)
        container.add_item(discord.ui.TextDisplay(self._summary_text()))
        container.add_item(discord.ui.Separator())

        category_select = discord.ui.Select(
            placeholder=f"Category: {self.category}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=c, value=c, default=(c == self.category))
                for c in SUGGESTION_CATEGORIES
            ],
        )
        category_select.callback = self._on_category
        cat_row = discord.ui.ActionRow()
        cat_row.add_item(category_select)
        container.add_item(cat_row)

        edit_btn = discord.ui.Button(
            label="Edit Details",
            style=discord.ButtonStyle.primary,
            emoji="📝",
        )
        edit_btn.callback = self._on_edit

        anon_btn = discord.ui.Button(
            label="Anonymous: On" if self.anonymous else "Anonymous: Off",
            style=discord.ButtonStyle.success if self.anonymous else discord.ButtonStyle.secondary,
            emoji="🕵️",
        )
        anon_btn.callback = self._on_toggle_anon

        controls_row = discord.ui.ActionRow()
        controls_row.add_item(edit_btn)
        controls_row.add_item(anon_btn)
        container.add_item(controls_row)

        submit_btn = discord.ui.Button(
            label="Submit",
            style=discord.ButtonStyle.success,
            emoji="✅",
        )
        submit_btn.callback = self._on_submit

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="✖️",
        )
        cancel_btn.callback = self._on_cancel

        action_row = discord.ui.ActionRow()
        action_row.add_item(submit_btn)
        action_row.add_item(cancel_btn)
        container.add_item(action_row)

        self.add_item(container)

    # ---- guards --------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This suggestion form belongs to someone else. Run `/suggest` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    # ---- component callbacks ------------------------------------------

    async def _on_category(self, interaction: discord.Interaction):
        values = interaction.data.get("values") if interaction.data else None
        if values:
            self.category = values[0]
            logger.debug(f"Builder category set to {self.category} by user {interaction.user.id}")
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_toggle_anon(self, interaction: discord.Interaction):
        self.anonymous = not self.anonymous
        logger.debug(f"Builder anonymity toggled to {self.anonymous} by user {interaction.user.id}")
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_edit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestionBuilderModal(self))

    async def _on_submit(self, interaction: discord.Interaction):
        if not self.draft_title or not self.draft_description:
            await interaction.response.send_message(
                "Please add a title and description first using **Edit Details**.",
                ephemeral=True,
            )
            return

        suggestion_text = self._compose_text()
        logger.info(
            f"Builder submission by user {interaction.user.id} - Category: {self.category}, "
            f"Anonymous: {self.anonymous}, Length: {len(suggestion_text)} chars")

        # Close out the builder message, then run the normal processing path.
        closing = discord.ui.LayoutView()
        closing.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("Submitting your suggestion..."),
                accent_color=0x5865F2,
            )
        )
        await interaction.response.edit_message(view=closing)
        self.stop()

        await self.cog._process_suggestion(
            interaction, suggestion_text, self.anonymous, self.category, already_responded=True
        )

    async def _on_cancel(self, interaction: discord.Interaction):
        cancelled = discord.ui.LayoutView()
        cancelled.add_item(discord.ui.TextDisplay("Suggestion cancelled."))
        await interaction.response.edit_message(view=cancelled)
        self.stop()


class SuggestionBrowserView(discord.ui.LayoutView):
    """Ephemeral Components v2 browser over one guild's suggestions.

    Author-locked and short-lived, following the builder above: `render()`
    rebuilds the container from scratch on every state change. Two properties
    this view exists to get right:

    - Each page is its own database query (server-side skip/limit), so a result
      set larger than one page is actually reachable.
    - The footer's total comes from a count over the SAME filter document the
      page query used, so the number it prints is the real number of matches and
      not however many rows happened to be fetched.

    Anonymous suggestions store no user_id, so they can never appear under the
    "Mine only" toggle. That is intended, and the empty state says so rather than
    letting it read as a bug.
    """

    PAGE_SIZE = 5

    def __init__(
        self,
        cog: "SuggestionCog",
        author_id: int,
        guild_id: int,
        query: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        filter_author_id: Optional[int] = None,
        mine: bool = False,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.query = query or None
        self.category = category if category in BROWSE_CATEGORY_OPTIONS else "All"
        self.status = status if status in BROWSE_STATUS_OPTIONS else "All"
        # Seeded from the command's `author` option; the Mine toggle overrides it.
        self.filter_author_id = filter_author_id
        self.mine = mine
        self.page = 1
        self.total = 0
        self.items: List[Dict[str, Any]] = []
        self.vote_totals: Dict[str, int] = {}
        # Render immediately so the view is always in a sendable state; `load()`
        # refetches and re-renders with real data before it is ever sent.
        self.render()

    # ---- state ---------------------------------------------------------

    @property
    def author_filter(self) -> Optional[int]:
        """Whose suggestions to show: the caller while Mine only is on, otherwise
        whoever was passed to the command's author option (None means everyone)."""
        return self.author_id if self.mine else self.filter_author_id

    @property
    def page_count(self) -> int:
        """Number of pages the current total spans; at least 1 so an empty result
        set still reads as "page 1 of 1" rather than "page 1 of 0"."""
        return max(1, (self.total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

    def _has_filters(self) -> bool:
        return bool(
            self.query
            or self.category != "All"
            or self.status != "All"
            or self.mine
            or self.filter_author_id
        )

    # ---- data ----------------------------------------------------------

    async def _fetch(self):
        """Pull the current page and the exact total for the current filters."""
        result = await self.cog.db_manager.browse_suggestions(
            page=self.page,
            page_size=self.PAGE_SIZE,
            query=self.query,
            category=self.category,
            status=self.status,
            author_id=self.author_filter,
            guild_id=self.guild_id,
        )
        self.items = result.get("items", [])
        self.total = result.get("total", 0)

    async def load(self):
        """Fetch the page, its vote counts, and rebuild the layout."""
        with PerformanceLogger(logger, "suggestion_browser_load"):
            await self._fetch()

            # A page can fall off the end when suggestions are removed between
            # renders. Step back to the last page that exists rather than showing
            # an empty screen over a non-empty result set.
            if not self.items and self.total > 0 and self.page > self.page_count:
                logger.debug(
                    f"Suggestion browser page {self.page} is past the end "
                    f"({self.total} results); falling back to page {self.page_count}"
                )
                self.page = self.page_count
                await self._fetch()

            suggestion_ids = [
                s["suggestion_id"] for s in self.items if s.get("suggestion_id")
            ]
            self.vote_totals = await self.cog.db_manager.get_vote_totals(suggestion_ids)
            self.render()

    # ---- state -> text -------------------------------------------------

    def _filter_text(self) -> str:
        bits = []
        if self.query:
            bits.append(f"Search: `{self.query}`")
        if self.category != "All":
            bits.append(f"Category: {self.category}")
        if self.status != "All":
            bits.append(f"Status: {self.status}")
        if self.mine:
            bits.append("Mine only")
        elif self.filter_author_id:
            bits.append(f"Author: <@{self.filter_author_id}>")
        return " | ".join(bits) if bits else "No filters - showing everything"

    def _row_text(self, position: int, suggestion: Dict[str, Any]) -> str:
        text = suggestion.get("text") or ""
        preview = text[:100] + "..." if len(text) > 100 else text
        suggestion_id = suggestion.get("suggestion_id") or ""
        votes = self.vote_totals.get(suggestion_id, 0)
        return (
            f"**{position}. {suggestion.get('status', 'Pending')} - "
            f"{suggestion.get('category', 'Other')}**\n"
            f"**ID:** {suggestion_id[:8]} | **Votes:** {votes}\n"
            f"{preview}"
        )

    def _empty_text(self) -> str:
        if self.mine:
            return (
                "You have no suggestions matching these filters.\n"
                "Anonymous suggestions are not linked to your account, so they never "
                "show up here."
            )
        if self._has_filters():
            return "No suggestions match these filters."
        return "No suggestions have been submitted on this server yet."

    def _footer_text(self) -> str:
        noun = "result" if self.total == 1 else "results"
        return f"-# Page {self.page} of {self.page_count} - {self.total} {noun}"

    # ---- rendering -----------------------------------------------------

    def render(self):
        """Rebuild the layout to reflect the current page and filters."""
        self.clear_items()

        container = discord.ui.Container(accent_color=0x5865F2)
        container.add_item(
            discord.ui.TextDisplay(f"## Suggestions\n{self._filter_text()}")
        )
        container.add_item(discord.ui.Separator())

        if self.items:
            first = (self.page - 1) * self.PAGE_SIZE + 1
            for position, suggestion in enumerate(self.items, start=first):
                container.add_item(discord.ui.TextDisplay(self._row_text(position, suggestion)))
        else:
            container.add_item(discord.ui.TextDisplay(self._empty_text()))

        container.add_item(discord.ui.Separator())

        category_select = discord.ui.Select(
            placeholder=f"Category: {self.category}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=c, value=c, default=(c == self.category))
                for c in BROWSE_CATEGORY_OPTIONS
            ],
        )
        category_select.callback = self._on_category
        category_row = discord.ui.ActionRow()
        category_row.add_item(category_select)
        container.add_item(category_row)

        status_select = discord.ui.Select(
            placeholder=f"Status: {self.status}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=s, value=s, default=(s == self.status))
                for s in BROWSE_STATUS_OPTIONS
            ],
        )
        status_select.callback = self._on_status
        status_row = discord.ui.ActionRow()
        status_row.add_item(status_select)
        container.add_item(status_row)

        prev_btn = discord.ui.Button(
            label="Prev",
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.page <= 1,
        )
        prev_btn.callback = self._on_prev

        next_btn = discord.ui.Button(
            label="Next",
            style=discord.ButtonStyle.secondary,
            emoji="▶️",
            disabled=self.page >= self.page_count,
        )
        next_btn.callback = self._on_next

        mine_btn = discord.ui.Button(
            label="Mine only: On" if self.mine else "Mine only: Off",
            style=discord.ButtonStyle.success if self.mine else discord.ButtonStyle.secondary,
            emoji="🙋",
        )
        mine_btn.callback = self._on_toggle_mine

        controls_row = discord.ui.ActionRow()
        controls_row.add_item(prev_btn)
        controls_row.add_item(next_btn)
        controls_row.add_item(mine_btn)
        container.add_item(controls_row)

        container.add_item(discord.ui.TextDisplay(self._footer_text()))

        self.add_item(container)

    # ---- guards --------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This suggestion browser belongs to someone else. "
                "Run `/suggestions` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    # ---- component callbacks ------------------------------------------

    async def _reload(self, interaction: discord.Interaction):
        await self.load()
        await interaction.response.edit_message(view=self)

    async def _on_category(self, interaction: discord.Interaction):
        values = interaction.data.get("values") if interaction.data else None
        if values:
            self.category = values[0]
            logger.debug(
                f"Suggestion browser category set to {self.category} by user {interaction.user.id}")
        # A filter change invalidates the current page number.
        self.page = 1
        await self._reload(interaction)

    async def _on_status(self, interaction: discord.Interaction):
        values = interaction.data.get("values") if interaction.data else None
        if values:
            self.status = values[0]
            logger.debug(
                f"Suggestion browser status set to {self.status} by user {interaction.user.id}")
        self.page = 1
        await self._reload(interaction)

    async def _on_toggle_mine(self, interaction: discord.Interaction):
        self.mine = not self.mine
        logger.debug(
            f"Suggestion browser 'Mine only' toggled to {self.mine} by user {interaction.user.id}")
        self.page = 1
        await self._reload(interaction)

    async def _on_prev(self, interaction: discord.Interaction):
        if self.page > 1:
            self.page -= 1
        await self._reload(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        if self.page < self.page_count:
            self.page += 1
        await self._reload(interaction)


class SuggestionDatabaseManager:
    """
    Database manager adapter that uses the new DatabaseManager for suggestions.
    This maintains backward compatibility while using the new database architecture.
    """

    def __init__(self, mongo_uri: str = None):
        logger.info("Initializing SuggestionDatabaseManager with new DatabaseManager")
        # We don't need the mongo_uri parameter anymore since we use the global db_manager
        self.db_manager = db_manager
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the database manager is initialized"""
        if not self._initialized:
            if not self.db_manager._initialized:
                await self.db_manager.initialize()
            self._initialized = True

    async def create_suggestion(self, user_id: int, text: str, anonymous: bool = False,
                                category: str = "Other", message_id: int = None,
                                thread_id: int = None, guild_id: int = None) -> str:
        """Create a new suggestion in the database"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "create_suggestion"):
            suggestion_id = str(uuid.uuid4())

            logger.info(
                f"Creating suggestion for user {user_id if not anonymous else 'anonymous'} - Category: {category}, Guild: {guild_id}, Length: {len(text)} chars")

            # Snowflake IDs are stored in the canonical string form.
            suggestion_doc = {
                "suggestion_id": suggestion_id,
                "guild_id": str(guild_id) if guild_id is not None else None,
                "user_id": str(user_id) if not anonymous and user_id is not None else None,
                "text": text,
                "anonymous": anonymous,
                "category": category,
                "status": "Pending",
                "priority": "Medium",
                "message_id": str(message_id) if message_id is not None else None,
                "thread_id": str(thread_id) if thread_id is not None else None,
                "admin_notes": "",
                "implementation_date": None,
                "tags": []
            }

            try:
                await self.db_manager.suggestions_suggestions.create_one(suggestion_doc)

                # Update user statistics
                if not anonymous:
                    await self._update_user_stats(user_id, "suggestions_submitted")

                logger.info(f"Successfully created suggestion {suggestion_id} for user {user_id}")
                return suggestion_id

            except Exception as e:
                logger.error(f"Error creating suggestion: {e}", exc_info=True)
                raise

    async def add_vote(self, suggestion_id: str, user_id: int, vote_type: str) -> Dict[str, Any]:
        """Add or update a vote for a suggestion"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "add_vote"):
            logger.debug(f"Processing {vote_type} vote from user {user_id} for suggestion {suggestion_id}")

            try:
                uid = str(user_id)
                # Check if user already voted
                existing_vote = await self.db_manager.suggestions_votes.find_one({
                    "suggestion_id": suggestion_id,
                    "user_id": uid
                })

                vote_doc = {
                    "suggestion_id": suggestion_id,
                    "user_id": uid,
                    "vote_type": vote_type
                }

                if existing_vote:
                    if existing_vote["vote_type"] == vote_type:
                        # Remove vote if same type
                        await self.db_manager.suggestions_votes.delete_one({
                            "suggestion_id": suggestion_id,
                            "user_id": uid
                        })
                        logger.info(f"Removed {vote_type} vote from user {user_id} for suggestion {suggestion_id}")
                        return {"success": True, "message": f"Removed your {vote_type} vote"}
                    else:
                        # Update vote type
                        await self.db_manager.suggestions_votes.update_one(
                            {"suggestion_id": suggestion_id, "user_id": uid},
                            {"$set": {"vote_type": vote_type}}
                        )
                        logger.info(
                            f"Changed vote from {existing_vote['vote_type']} to {vote_type} for user {user_id} on suggestion {suggestion_id}")
                        return {"success": True, "message": f"Changed vote to {vote_type}"}
                else:
                    # Add new vote
                    await self.db_manager.suggestions_votes.create_one(vote_doc)
                    await self._update_user_stats(user_id, "votes_cast")
                    logger.info(f"Added new {vote_type} vote from user {user_id} for suggestion {suggestion_id}")
                    return {"success": True, "message": f"Added {vote_type} vote"}

            except Exception as e:
                logger.error(f"Error adding vote: {e}", exc_info=True)
                return {"success": False, "message": "Failed to process vote"}

    async def get_vote_counts(self, suggestion_id: str) -> Dict[str, int]:
        """Get vote counts for a suggestion"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "get_vote_counts"):
            try:
                pipeline = [
                    {"$match": {"suggestion_id": suggestion_id}},
                    {"$group": {"_id": "$vote_type", "count": {"$sum": 1}}}
                ]

                results = await self.db_manager.suggestions_votes.aggregate(pipeline)
                vote_counts = {result["_id"]: result["count"] for result in results}

                logger.debug(f"Retrieved vote counts for suggestion {suggestion_id}: {vote_counts}")
                return vote_counts

            except Exception as e:
                logger.error(f"Error getting vote counts: {e}", exc_info=True)
                return {}

    async def get_suggestion_id_from_message(self, message_id: int) -> Optional[str]:
        """Resolve a suggestion_id from the message its buttons live on.

        The persistent vote view is registered on startup without a suggestion_id,
        so after a bot restart it recovers the id from the message (mirrors the
        WYR view's message->question fallback).
        """
        await self._ensure_initialized()
        try:
            doc = await self.db_manager.suggestions_suggestions.find_one(
                {"message_id": str(message_id)}
            )
            return doc.get("suggestion_id") if doc else None
        except Exception as e:
            logger.error(
                f"Error resolving suggestion from message {message_id}: {e}",
                exc_info=True,
            )
            return None

    @staticmethod
    def _build_search_filter(query: str = None, category: str = None,
                             status: str = None, author_id: int = None,
                             guild_id: int = None) -> Dict[str, Any]:
        """Build the Mongo filter shared by search, paged browse, and the browse count.

        One builder so a page query and the count that labels it are guaranteed to
        be looking at the same documents - a filter that drifts between the two is
        exactly how a footer starts reporting a total that is not the total.

        Snowflakes are stored as strings, so every id is cast; an int matches
        nothing, silently.
        """
        filter_doc: Dict[str, Any] = {}

        if guild_id:
            filter_doc["guild_id"] = str(guild_id)
        if query:
            filter_doc["$text"] = {"$search": query}
        if category and category != "All":
            filter_doc["category"] = category
        if status and status != "All":
            filter_doc["status"] = status
        if author_id:
            filter_doc["user_id"] = str(author_id)

        return filter_doc

    async def search_suggestions(self, query: str = None, category: str = None,
                                 status: str = None, author_id: int = None,
                                 limit: int = 10, guild_id: int = None) -> List[Dict]:
        """Search suggestions with filters"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "search_suggestions"):
            search_params = {
                "query": query,
                "category": category,
                "status": status,
                "author_id": author_id,
                "limit": limit,
                "guild_id": guild_id
            }
            logger.info(f"Searching suggestions with parameters: {search_params}")

            try:
                filter_doc = self._build_search_filter(
                    query=query,
                    category=category,
                    status=status,
                    author_id=author_id,
                    guild_id=guild_id,
                )

                results = await self.db_manager.suggestions_suggestions.find_many(
                    filter_dict=filter_doc,
                    limit=limit,
                    sort=[("created_at", -1)]
                )

                logger.info(f"Search returned {len(results)} suggestions")
                return results

            except Exception as e:
                logger.error(f"Error searching suggestions: {e}", exc_info=True)
                return []

    async def browse_suggestions(self, page: int = 1, page_size: int = 5,
                                 query: str = None, category: str = None,
                                 status: str = None, author_id: int = None,
                                 guild_id: int = None) -> Dict[str, Any]:
        """Fetch ONE page of suggestions plus the exact total for the same filters.

        Paging is done server-side (skip/limit) so the whole result set is never
        pulled back to be sliced in memory, and the total is a count over the very
        same filter document the page was fetched with.

        Returns ``{"items": [...], "total": int}``.
        """
        await self._ensure_initialized()

        with PerformanceLogger(logger, "browse_suggestions"):
            page = max(1, int(page))
            page_size = max(1, int(page_size))

            filter_doc = self._build_search_filter(
                query=query,
                category=category,
                status=status,
                author_id=author_id,
                guild_id=guild_id,
            )
            logger.info(
                f"Browsing suggestions page {page} (size {page_size}) with filter: {filter_doc}")

            try:
                total = await self.db_manager.suggestions_suggestions.count_documents(filter_doc)
                items = await self.db_manager.suggestions_suggestions.find_many(
                    filter_dict=filter_doc,
                    skip=(page - 1) * page_size,
                    limit=page_size,
                    sort=[("created_at", -1)]
                )

                logger.info(f"Browse returned {len(items)} of {total} suggestions")
                return {"items": items, "total": total}

            except Exception as e:
                logger.error(f"Error browsing suggestions: {e}", exc_info=True)
                return {"items": [], "total": 0}

    async def get_vote_totals(self, suggestion_ids: List[str]) -> Dict[str, int]:
        """Total vote count for each of several suggestions, in ONE aggregation.

        Rendering a browse page needs one number per row; asking per row is one
        round trip per row. ``get_vote_counts`` stays as it is - the vote buttons
        need the per-type breakdown for a single suggestion, which this does not
        return.
        """
        await self._ensure_initialized()

        if not suggestion_ids:
            return {}

        with PerformanceLogger(logger, "get_vote_totals"):
            try:
                pipeline = [
                    {"$match": {"suggestion_id": {"$in": list(suggestion_ids)}}},
                    {"$group": {"_id": "$suggestion_id", "count": {"$sum": 1}}}
                ]

                results = await self.db_manager.suggestions_votes.aggregate(pipeline)
                totals = {result["_id"]: result["count"] for result in results}

                logger.debug(
                    f"Retrieved vote totals for {len(suggestion_ids)} suggestions: {totals}")
                return totals

            except Exception as e:
                logger.error(f"Error getting vote totals: {e}", exc_info=True)
                return {}

    async def get_user_suggestions(self, user_id: int, limit: int = 10, guild_id: int = None) -> List[Dict]:
        """Get suggestions by a specific user"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "get_user_suggestions"):
            logger.info(f"Retrieving suggestions for user {user_id} in guild {guild_id} (limit: {limit})")

            try:
                filter_dict = {"user_id": str(user_id)}
                if guild_id:
                    filter_dict["guild_id"] = str(guild_id)
                results = await self.db_manager.suggestions_suggestions.find_many(
                    filter_dict=filter_dict,
                    limit=limit,
                    sort=[("created_at", -1)]
                )
                logger.info(f"Found {len(results)} suggestions for user {user_id}")
                return results
            except Exception as e:
                logger.error(f"Error getting user suggestions: {e}", exc_info=True)
                return []

    async def get_suggestion_stats(self, guild_id: int = None) -> Dict[str, Any]:
        """Get suggestion statistics, optionally scoped to a guild"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "get_suggestion_stats"):
            logger.info(f"Generating suggestion statistics for guild {guild_id}")

            try:
                match_filter = {}
                if guild_id:
                    match_filter["guild_id"] = str(guild_id)

                total_suggestions = await self.db_manager.suggestions_suggestions.count_documents(match_filter)

                # Status distribution
                status_pipeline = []
                if match_filter:
                    status_pipeline.append({"$match": match_filter})
                status_pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
                status_results = await self.db_manager.suggestions_suggestions.aggregate(status_pipeline)
                status_dist = {result["_id"]: result["count"] for result in status_results}

                # Category distribution
                category_pipeline = []
                if match_filter:
                    category_pipeline.append({"$match": match_filter})
                category_pipeline.append({"$group": {"_id": "$category", "count": {"$sum": 1}}})
                category_results = await self.db_manager.suggestions_suggestions.aggregate(category_pipeline)
                category_dist = {result["_id"]: result["count"] for result in category_results}

                # Top contributors
                contributor_match = {"anonymous": False}
                if guild_id:
                    contributor_match["guild_id"] = str(guild_id)
                contributor_pipeline = [
                    {"$match": contributor_match},
                    {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 5}
                ]
                contributor_results = await self.db_manager.suggestions_suggestions.aggregate(contributor_pipeline)

                stats = {
                    "total_suggestions": total_suggestions,
                    "status_distribution": status_dist,
                    "category_distribution": category_dist,
                    "top_contributors": contributor_results
                }

                logger.info(
                    f"Generated stats: {total_suggestions} total suggestions, {len(status_dist)} statuses, {len(category_dist)} categories")
                return stats

            except Exception as e:
                logger.error(f"Error getting suggestion stats: {e}", exc_info=True)
                return {}

    async def _update_user_stats(self, user_id: int, stat_type: str):
        """Update user statistics"""
        try:
            await self.db_manager.get_collection_manager('suggestions_userstats').update_one(
                {"user_id": str(user_id)},
                {
                    "$inc": {stat_type: 1},
                    "$set": {"last_activity": datetime.utcnow()}
                },
                upsert=True
            )
            logger.debug(f"Updated {stat_type} stat for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating user stats: {e}", exc_info=True)

    async def get_pending_notifications(self) -> List[Dict]:
        """Get pending notifications"""
        await self._ensure_initialized()

        try:
            notifications = await self.db_manager.get_collection_manager('suggestions_notification_queue').find_many(
                {"sent": False})
            logger.debug(f"Retrieved {len(notifications)} pending notifications")
            return notifications
        except Exception as e:
            logger.error(f"Error getting pending notifications: {e}", exc_info=True)
            return []

    async def mark_notification_sent(self, notification_id):
        """Mark notification as sent"""
        try:
            await self.db_manager.get_collection_manager('suggestions_notification_queue').update_one(
                {"_id": notification_id},
                {"$set": {"sent": True, "sent_at": datetime.utcnow()}}
            )
            logger.debug(f"Marked notification {notification_id} as sent")
        except Exception as e:
            logger.error(f"Error marking notification as sent: {e}", exc_info=True)

    # Legacy compatibility methods for direct collection access
    @property
    def suggestions(self):
        """Legacy access to suggestions collection"""
        return self.db_manager.get_raw_collection('Suggestions', 'Suggestions')


class SuggestionCog(commands.Cog):
    def __init__(self, bot):
        logger.info("Initializing SuggestionCog with new DatabaseManager")
        self.bot = bot

        # Initialize database connection using the new DatabaseManager
        try:
            self.db_manager = SuggestionDatabaseManager()
            logger.info("Successfully initialized suggestion database manager")
        except Exception as e:
            logger.error(f"Failed to initialize suggestion database manager: {e}", exc_info=True)
            raise

        # Start notification task
        self.notification_task.start()
        logger.info("SuggestionCog initialization completed")

    # ==================== Standalone Commands ====================

    @app_commands.command(name="suggest", description="Submit a suggestion (opens a form, or pass text directly)")
    @app_commands.guild_only()
    @app_commands.describe(
        suggestion_text="The text of your suggestion",
        anonymous="Submit anonymously",
        category="Category for your suggestion",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Bot Feature", value="Bot Feature"),
            app_commands.Choice(name="Server Improvement", value="Server Improvement"),
            app_commands.Choice(name="Event Idea", value="Event Idea"),
            app_commands.Choice(name="Rule Change", value="Rule Change"),
            app_commands.Choice(name="Other", value="Other"),
        ],
    )
    @app_commands.checks.cooldown(1, 30)
    async def suggest_command(
            self,
            interaction: discord.Interaction,
            suggestion_text: Optional[str] = None,
            anonymous: bool = False,
            category: str = "Other",
    ):
        """Submit a suggestion.

        Hybrid behavior:
        - `suggestion_text` set -> post directly using the given options (quick path).
        - nothing set -> open the interactive Components v2 builder, seeded with
          any category/anonymous options that were supplied.
        """
        if suggestion_text:
            logger.info(
                f"Suggestion submission by {interaction.user.id} - Category: {category}, Anonymous: {anonymous}")
            await self._process_suggestion(interaction, suggestion_text, anonymous, category)
        else:
            logger.info(f"Interactive builder opened by {interaction.user.id}")
            view = SuggestionBuilderView(
                self,
                interaction.user.id,
                initial_category=category,
                initial_anonymous=anonymous,
            )
            await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="suggestions", description="Browse and search this server's suggestions")
    @app_commands.guild_only()
    @app_commands.describe(
        query="Search terms",
        category="Filter by category",
        status="Filter by status",
        author="Filter by author (mention them)"
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="All", value="All"),
            app_commands.Choice(name="Bot Feature", value="Bot Feature"),
            app_commands.Choice(name="Server Improvement", value="Server Improvement"),
            app_commands.Choice(name="Event Idea", value="Event Idea"),
            app_commands.Choice(name="Rule Change", value="Rule Change"),
            app_commands.Choice(name="Other", value="Other"),
        ],
        status=[
            app_commands.Choice(name="All", value="All"),
            app_commands.Choice(name="Pending", value="Pending"),
            app_commands.Choice(name="Under Review", value="Under Review"),
            app_commands.Choice(name="Approved", value="Approved"),
            app_commands.Choice(name="Implemented", value="Implemented"),
            app_commands.Choice(name="Rejected", value="Rejected"),
            app_commands.Choice(name="On Hold", value="On Hold"),
        ],
    )
    async def suggestions_command(
            self,
            interaction: discord.Interaction,
            query: Optional[str] = None,
            category: Optional[str] = None,
            status: Optional[str] = None,
            author: Optional[discord.Member] = None,
    ):
        """Browse this server's suggestions in a paged, filterable browser.

        The options only SEED the browser: category, status, whose suggestions
        ("Mine only") and the page are all adjustable from the message itself.
        Always ephemeral - the suggestions themselves live in the suggestions
        channel, this is only a lookup tool.
        """
        logger.info(
            f"Suggestions browser opened by {interaction.user.id} - Query: '{query}', Category: {category}, Status: {status}, Author: {author.id if author else None}")
        await interaction.response.defer(ephemeral=True)

        view = SuggestionBrowserView(
            self,
            interaction.user.id,
            interaction.guild.id,
            query=query,
            category=category,
            status=status,
            filter_author_id=author.id if author else None,
        )
        await view.load()

        if view.total == 0:
            logger.info(f"Suggestions browser returned no results for user {interaction.user.id}")
            # An empty result on a server that never set a channel is a setup gap,
            # not a failed search - say which one it is.
            guild_config = await get_config(interaction.guild.id)
            if not guild_config.suggestions["channel_id"]:
                await send_setup_notice(
                    interaction,
                    what="suggestions",
                    path="Suggestions -> Suggestion Channel",
                    detail="There is nothing to search yet.",
                )
                return

        logger.info(
            f"Suggestions browser sent to user {interaction.user.id}: {view.total} total results")
        await interaction.followup.send(view=view, ephemeral=True)

    def cog_unload(self):
        logger.info("Unloading SuggestionCog")
        self.notification_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Add persistent views when bot starts (once; on_ready refires on every
        gateway reconnect, so guard against re-initializing each time)."""
        if getattr(self, "_ready_done", False):
            return
        self._ready_done = True
        logger.info("Adding persistent views for suggestion system")
        # Initialize database manager on bot ready
        await self.db_manager._ensure_initialized()
        self.bot.add_view(SuggestionView("", self.db_manager))

    async def _process_suggestion(self, interaction: discord.Interaction,
                                  suggestion_text: str, anonymous: bool, category: str,
                                  already_responded: bool = False):
        """Process suggestion submission.

        already_responded=True when called from the interactive builder, whose
        Submit button has already edited the builder message (consuming the
        interaction response). In that case we skip the defer and rely on
        followups only.
        """
        with log_context(logger, f"process_suggestion_{category}"):
            user = interaction.user

            # A member who has turned data collection off can still suggest, but
            # the suggestion cannot carry their id, so it is forced anonymous
            # whatever they picked. Decided here, before the defer, so the post,
            # the thread and the confirmation all follow the one path.
            forced_anonymous = await _opted_out(interaction.client, user.id)
            if forced_anonymous:
                anonymous = True

            logger.info(
                f"Processing suggestion from user {user.id} - Category: {category}, Anonymous: {anonymous}, Length: {len(suggestion_text)} chars")

            if not already_responded:
                await interaction.response.defer(ephemeral=anonymous)

            if len(suggestion_text) > 2000:
                logger.warning(f"Suggestion from user {user.id} rejected - too long ({len(suggestion_text)} chars)")
                await interaction.followup.send(
                    "❌ Your suggestion is too long. Please keep it under 2000 characters.",
                    ephemeral=True
                )
                return

            # Fail early rather than after the duplicate-check dialog, so nobody
            # works through "Submit Anyway" only to learn there is nowhere to post.
            if await self._require_suggestions_channel(interaction) is None:
                return

            # Check for similar suggestions within this guild
            similar_suggestions = await self.db_manager.search_suggestions(suggestion_text[:50], limit=3, guild_id=interaction.guild.id)
            if similar_suggestions:
                logger.info(f"Found {len(similar_suggestions)} similar suggestions for user {user.id}'s submission")
                similar_list = "\n".join([f"• {s['text'][:100]}..." for s in similar_suggestions[:3]])
                embed = discord.Embed(
                    title="⚠️ Similar Suggestions Found",
                    description=f"Found {len(similar_suggestions)} similar suggestions:\n\n{similar_list}",
                    color=discord.Color.orange()
                )
                view = discord.ui.View()

                async def continue_anyway(interaction_inner):
                    logger.info(f"User {user.id} chose to submit despite similar suggestions")
                    await interaction_inner.response.defer()
                    await self._create_suggestion_post(
                        interaction, suggestion_text, anonymous, category,
                        forced_anonymous=forced_anonymous,
                    )

                async def cancel_suggestion(interaction_inner):
                    logger.info(f"User {user.id} cancelled submission after seeing similar suggestions")
                    await interaction_inner.response.send_message("✅ Suggestion cancelled.", ephemeral=True)

                continue_btn = discord.ui.Button(label="Submit Anyway",
                                                 style=cast(discord.ButtonStyle, discord.ButtonStyle.success))
                cancel_btn = discord.ui.Button(label="Cancel",
                                               style=cast(discord.ButtonStyle, discord.ButtonStyle.danger))
                continue_btn.callback = continue_anyway
                cancel_btn.callback = cancel_suggestion

                view.add_item(continue_btn)
                view.add_item(cancel_btn)

                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                logger.info(f"No similar suggestions found for user {user.id}'s submission, proceeding directly")
                await self._create_suggestion_post(
                    interaction, suggestion_text, anonymous, category,
                    forced_anonymous=forced_anonymous,
                )

    async def _require_suggestions_channel(self, interaction: discord.Interaction):
        """Return the guild's suggestions channel, or None after telling the member why not.

        Checked before a suggestion is stored so an unconfigured server never
        accumulates suggestions that were never posted anywhere.
        """
        guild_config = await get_config(interaction.guild.id)
        channel = self.bot.get_channel(guild_config.suggestions["channel_id"])
        if channel:
            return channel

        logger.warning(
            f"Suggestion by {interaction.user.id} blocked - no usable suggestions "
            f"channel in guild {interaction.guild.id}"
        )
        await send_setup_notice(
            interaction,
            what="a suggestions channel",
            path="Suggestions -> Suggestion Channel",
            detail=(
                "Your suggestion was not submitted, because there is nowhere to post "
                "it yet. Nothing was lost - send it again once the channel is set."
            ),
        )
        return None

    async def _create_suggestion_post(self, interaction: discord.Interaction,
                                      suggestion_text: str, anonymous: bool, category: str,
                                      forced_anonymous: bool = False):
        """Create the actual suggestion post.

        ``forced_anonymous`` means the member did not choose anonymity, it was
        applied because they have turned data collection off. It changes nothing
        about what is stored (that is already the plain anonymous path) - it only
        changes the confirmation, so nobody is left wondering why their name is
        missing or why the status DMs never arrive.
        """
        with PerformanceLogger(logger, "create_suggestion_post"):
            user = interaction.user
            logger.info(f"Creating suggestion post for user {user.id} - Category: {category}, Anonymous: {anonymous}")

            try:
                # Get per-guild config for channel IDs
                guild_config = await get_config(interaction.guild.id)

                # Resolve the destination BEFORE writing anything. Creating the
                # record first would leave an orphaned suggestion in the database
                # with no post to vote on whenever the channel is unset or gone.
                suggestions_channel = await self._require_suggestions_channel(interaction)
                if suggestions_channel is None:
                    return

                # Create suggestion in database
                suggestion_id = await self.db_manager.create_suggestion(
                    user.id, suggestion_text, anonymous, category, guild_id=interaction.guild.id
                )

                # Prepare embeds
                status_colors = {
                    "Pending": discord.Color.blue(),
                    "Under Review": discord.Color.orange(),
                    "Approved": discord.Color.green(),
                    "Implemented": discord.Color.gold(),
                    "Rejected": discord.Color.red(),
                    "On Hold": discord.Color.purple()
                }

                public_embed = discord.Embed(
                    title="📬 New Suggestion",
                    description=suggestion_text,
                    color=status_colors.get("Pending", discord.Color.blue()),
                    timestamp=interaction.created_at,
                )

                public_embed.add_field(name="Category", value=category, inline=True)
                public_embed.add_field(name="Status", value="Pending", inline=True)
                public_embed.add_field(name="ID", value=suggestion_id[:8], inline=True)
                public_embed.add_field(name="Votes", value="👍 0 | 👎 0 | ❤️ 0 | 🤔 0", inline=False)

                if anonymous:
                    public_embed.set_author(name="Anonymous")
                    public_embed.set_footer(text="Submitted anonymously")
                else:
                    user_avatar_url = user.avatar.url if user.avatar else None
                    public_embed.set_author(name=user.display_name, icon_url=user_avatar_url)
                    public_embed.set_footer(text=f"Suggested by {user}", icon_url=user_avatar_url)

                # Admin embed
                admin_embed = discord.Embed(
                    title="📬 New Suggestion (Admin Copy)",
                    description=suggestion_text,
                    color=discord.Color.red(),
                    timestamp=interaction.created_at,
                )

                admin_embed.add_field(name="Category", value=category, inline=True)
                admin_embed.add_field(name="Anonymous", value=str(anonymous), inline=True)
                admin_embed.add_field(name="Suggestion ID", value=suggestion_id, inline=False)

                if forced_anonymous:
                    # The member opted out of being linked to what they post, and
                    # the privacy page tells them there is "no record tied to you".
                    # The admin copy used to name them anyway, which made that a
                    # false promise. Identity is not in the channel at all now; it
                    # is written to the audit log below, so moderating an abusive
                    # anonymous suggestion is a deliberate lookup rather than a
                    # name sitting in a channel every admin can read.
                    admin_embed.set_author(name="Anonymous (privacy opt-out)")
                    admin_embed.set_footer(
                        text="Author withheld. Look this Suggestion ID up in the "
                             "audit log if you need it."
                    )
                else:
                    user_avatar_url = user.avatar.url if user.avatar else None
                    admin_embed.set_author(name=user.display_name, icon_url=user_avatar_url)
                    admin_embed.add_field(name="User ID", value=f"{user.id}", inline=False)
                    admin_embed.set_footer(text=f"Suggested by {user}", icon_url=user_avatar_url)

                # Optional mirror of the suggestion for staff; absent on a server
                # that has not set an admin channel.
                admin_channel = self.bot.get_channel(guild_config.server["admin_channel_id"])

                # Create suggestion view
                view = SuggestionView(suggestion_id, self.db_manager)

                # Send to suggestions channel
                message = await suggestions_channel.send(
                    content="Anonymous Suggestion:" if anonymous else f"Suggestion from {user.mention}:",
                    embed=public_embed,
                    view=view
                )
                logger.info(f"Posted suggestion {suggestion_id} to suggestions channel (message {message.id})")

                # Create thread
                thread = await message.create_thread(
                    name=f"Discussion: {category} Suggestion"
                    if anonymous
                    else f"Discussion: {user.display_name}'s {category} Suggestion",
                    auto_archive_duration=4320,
                )

                thread_message = await thread.send(
                    content="Let's discuss this suggestion!"
                    if anonymous
                    else f"Let's discuss {user.mention}'s suggestion!"
                )
                logger.info(f"Created discussion thread {thread.id} for suggestion {suggestion_id}")

                # Update database with message and thread IDs
                await db_manager.suggestions_suggestions.update_one(
                    {"suggestion_id": suggestion_id},
                    {
                        "$set": {
                            "message_id": str(message.id),
                            "thread_id": str(thread.id)
                        }
                    }
                )
                logger.debug(f"Updated suggestion {suggestion_id} with message and thread IDs")

                # Send admin copy
                if admin_channel:
                    await admin_channel.send(embed=admin_embed)
                    logger.info(f"Sent admin copy of suggestion {suggestion_id} to admin channel")
                else:
                    logger.warning("Admin channel not found, admin copy not sent")

                # The author of a forced-anonymous suggestion is withheld from the
                # channel but recorded here, so an admin who needs it can look it
                # up by Suggestion ID. Best-effort: a failed audit write must not
                # cost the member their suggestion, which is already posted.
                if forced_anonymous:
                    try:
                        await write_anonymous_author_audit(
                            guild_id=interaction.guild_id,
                            suggestion_id=suggestion_id,
                            author=user,
                        )
                    except Exception as audit_error:
                        logger.error(
                            f"Failed to record the author of anonymous suggestion "
                            f"{suggestion_id}: {audit_error}",
                            exc_info=True,
                        )

                # Notify user
                success_message = f"✅ Your {'anonymous ' if anonymous else ''}suggestion has been posted! (ID: {suggestion_id[:8]})"
                if forced_anonymous:
                    success_message += (
                        "\n\nIt was posted anonymously because you have turned off "
                        "data collection, so it is not linked to your account. That "
                        "means you will not get status updates by direct message, it "
                        "will not show up in your stats or under your own "
                        "suggestions, and you cannot edit it. You can turn data "
                        "collection back on any time on the privacy page of the "
                        "dashboard."
                    )

                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(success_message, ephemeral=True)
                else:
                    await interaction.response.send_message(success_message, ephemeral=True)

                logger.info(f"Successfully processed suggestion {suggestion_id} for user {user.id}")

            except Exception as e:
                logger.error(f"Error creating suggestion post for user {user.id}: {e}", exc_info=True)

                error_message = "❌ An error occurred while processing your suggestion."
                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(error_message, ephemeral=True)
                else:
                    await interaction.response.send_message(error_message, ephemeral=True)

    @staticmethod
    def _notification_expired(notification: dict, max_age_hours: int = 24) -> bool:
        """True if a pending notification is old enough to abandon, so transient
        delivery failures can't keep it retrying every cycle forever."""
        created = notification.get("created_at")
        if not isinstance(created, datetime):
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > timedelta(hours=max_age_hours)

    @tasks.loop(minutes=5)
    async def notification_task(self):
        """Process pending notifications"""
        with log_context(logger, "notification_processing"):
            try:
                notifications = await self.db_manager.get_pending_notifications()

                if notifications:
                    logger.info(f"Processing {len(notifications)} pending notifications")

                for notification in notifications:
                    try:
                        # get_user is cache-only; fall back to the API so an uncached
                        # recipient isn't retried every 5 minutes forever. Stored user
                        # ids are strings; discord.py wants ints.
                        recipient_id = int(notification["user_id"])
                        user = self.bot.get_user(recipient_id)
                        if user is None:
                            try:
                                user = await self.bot.fetch_user(recipient_id)
                            except discord.NotFound:
                                # Account no longer exists -> stop retrying.
                                await self.db_manager.mark_notification_sent(notification["_id"])
                                logger.warning(
                                    f"User {notification['user_id']} no longer exists; abandoning notification")
                                continue
                            except discord.HTTPException as fetch_exc:
                                # Transient: retry next cycle, but give up if it has been
                                # pending too long so it can't loop indefinitely.
                                if self._notification_expired(notification):
                                    await self.db_manager.mark_notification_sent(notification["_id"])
                                    logger.warning(
                                        f"Notification {notification.get('_id')} expired after repeated "
                                        f"fetch failures ({fetch_exc}); abandoning")
                                else:
                                    logger.warning(
                                        f"Could not fetch user {notification['user_id']} ({fetch_exc}); will retry")
                                continue

                        embed = discord.Embed(
                            title="📬 Suggestion Update",
                            color=discord.Color.blue()
                        )
                        embed.add_field(
                            name="Suggestion ID",
                            value=notification["suggestion_id"][:8],
                            inline=True
                        )
                        embed.add_field(
                            name="New Status",
                            value=notification["status"],
                            inline=True
                        )
                        if notification.get("reason"):
                            embed.add_field(
                                name="Reason",
                                value=notification["reason"],
                                inline=False
                            )

                        try:
                            await user.send(embed=embed)
                            await self.db_manager.mark_notification_sent(notification["_id"])
                            logger.info(
                                f"Sent notification to user {notification['user_id']} for suggestion {notification['suggestion_id']}")
                        except discord.Forbidden:
                            # User has DMs disabled, mark as sent anyway
                            await self.db_manager.mark_notification_sent(notification["_id"])
                            logger.warning(
                                f"Could not send DM to user {notification['user_id']} (DMs disabled), marking as sent")

                    except Exception as e:
                        logger.error(f"Error sending notification {notification.get('_id')}: {e}", exc_info=True)
                        continue

            except Exception as e:
                logger.error(f"Error in notification task: {e}", exc_info=True)

    @notification_task.before_loop
    async def before_notification_task(self):
        logger.info("Waiting for bot to be ready before starting notification task")
        await self.bot.wait_until_ready()
        logger.info("Bot ready, notification task can now start")

    # Error handlers for group commands
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            logger.info(f"User {interaction.user.id} hit cooldown on suggestion command")
            await interaction.response.send_message(
                f"⏳ You're on cooldown! Please try again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            logger.error(f"Unhandled error in suggestion command for user {interaction.user.id}: {error}",
                         exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An unexpected error occurred. Please try again later.",
                    ephemeral=True
                )


async def setup(bot: commands.Bot):
    """Load the Cog"""
    logger.info("Setting up SuggestionCog")
    try:
        cog = SuggestionCog(bot)
        await bot.add_cog(cog)
        logger.info("SuggestionCog setup completed successfully")
    except Exception as e:
        logger.error(f"Failed to set up SuggestionCog: {e}", exc_info=True)
        raise
