"""
Question Bank admin-panel nodes.

Wires a guild's own daily questions into the WYR Settings group:

    WYR Settings -> Question Bank
      +- Add a Question       (action -> pick a type -> modal -> result)
      +- Import Questions     (file_upload, JSON, with a downloadable template)
      +- Browse and Delete    (paginated_list over this guild's own questions)
      +- Question Types       (option_select, multi - which formats get posted)
      +- Where Questions Come From  (option_select)

Before this existed there was no way to put a question into the bank at all
except by hand in Mongo, which is the gap the whole feature closes.

Modal submits respond with UPDATE_MESSAGE (``modal_interaction.response.edit_message``
via ``PanelFlow._render_via_modal``), which Discord permits because the modal is
opened from a component on message 2.
"""

from __future__ import annotations

import discord

from storage.log import get_logger

from Features.daily.wyr_bank import FORMAT_LABELS
from Features.daily.wyr_question_form import QuestionFormModal
from Features.daily.wyr_schema import build_import_template, validate_wyr_import_schema

from ..views.panel_engine import ActionContext, PanelNode
from ..views.wyr_question_views import (
    build_add_question_view,
    build_add_result_view,
)
from .panel_flow import PanelFlow
from .structure import member_action
from .wyr_question_actions import (
    QUESTION_FORMAT_OPTIONS,
    QUESTION_SOURCE_OPTIONS,
    WYRQuestionActions,
)

logger = get_logger("WYRQuestionNodes")

ADD_NODE_KEY = "wyr_add_question"
QUEUE_NODE_KEY = "wyr_review_queue"
BANK_NODE_KEY = "wyr_browse_questions"
IMPORT_NODE_KEY = "wyr_import_questions"


class _AddQuestionFlow(PanelFlow):
    """One admin's walk through adding a question by hand."""

    node_key = ADD_NODE_KEY
    audit_section = "wyr"

    def __init__(self, cog, guild, ctx, node):
        super().__init__(cog, guild, ctx, node)
        # Held for the life of this screen only. An age-restricted question is
        # rare enough that a toggle beats a field in every modal.
        self._nsfw = False

    # -- screens ----------------------------------------------------------

    async def _picker_layout(self) -> discord.ui.LayoutView:
        enabled = await WYRQuestionActions.get_question_formats(self.guild.id)
        return build_add_question_view(
            nsfw=self._nsfw,
            enabled_formats=enabled,
            on_pick=self._make_pick_handler,
            on_toggle_nsfw=self._on_toggle_nsfw,
            on_back=self._on_back,
            back_label=self.ctx.back_label,
        )

    async def open(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._picker_layout())

    # -- handlers ---------------------------------------------------------

    def _make_pick_handler(self, question_format: str):
        """Bind one handler per format button.

        A factory rather than a closure over a loop variable, which would leave
        every button opening the last format's modal.
        """
        async def _handler(interaction: discord.Interaction) -> None:
            modal = QuestionFormModal(
                question_format,
                self._make_submit_handler(question_format),
            )
            await interaction.response.send_modal(modal)
        return _handler

    def _make_submit_handler(self, question_format: str):
        async def _handler(interaction: discord.Interaction, text, options, tags) -> None:
            if not self._allowed(interaction):
                await self._too_fast(interaction)
                return

            ok, message, question = await WYRQuestionActions.add_question(
                self.guild.id, question_format, text, options, tags, nsfw=self._nsfw
            )
            if not ok:
                # Discord forbids answering a modal submit with another modal,
                # so the failure re-renders the picker and explains in a followup.
                await self._render_via_modal(interaction, await self._picker_layout())
                await self._notice(interaction, "That question was not added", message)
                return

            warning = await WYRQuestionActions.warning_for_format(
                self.guild.id, question_format
            )
            layout = build_add_result_view(
                message=f"✅ {message}",
                warning=warning,
                offer_format=question_format if warning else None,
                on_add_another=self._on_add_another,
                on_enable_format=(
                    self._make_enable_handler(question_format) if warning else None
                ),
                on_back=self._on_back,
                back_label=self.ctx.back_label,
            )
            await self._render_via_modal(interaction, layout)
            await self._after_write(
                interaction, "create", None, f"question {question['id']}"
            )
        return _handler

    def _make_enable_handler(self, question_format: str):
        async def _handler(interaction: discord.Interaction) -> None:
            if not self._allowed(interaction):
                await self._too_fast(interaction)
                return
            ok = await WYRQuestionActions.enable_format(self.guild.id, question_format)
            label = FORMAT_LABELS.get(question_format, question_format)
            if not ok:
                await self._notice(
                    interaction, "Could not turn that on",
                    f"**{label}** questions could not be turned on. Try the "
                    f"**Question Types** setting instead.",
                )
                return
            await self._render(interaction, await self._picker_layout())
            await self._notice(
                interaction, "Turned on",
                f"This server will now post **{label}** questions.",
            )
            await self._after_write(
                interaction, "update", None, f"question_formats += {question_format}"
            )
        return _handler

    async def _on_toggle_nsfw(self, interaction: discord.Interaction) -> None:
        self._nsfw = not self._nsfw
        await self._render(interaction, await self._picker_layout())

    async def _on_add_another(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._picker_layout())

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await self._back_to_parent(interaction)


async def _run_add_question(cog, interaction: discord.Interaction,
                            guild: discord.Guild, ctx: ActionContext) -> None:
    node = build_wyr_add_question_node()
    await _AddQuestionFlow(cog, guild, ctx, node).open(interaction)


async def _import_post_save(interaction: discord.Interaction, guild_id: int,
                            _saved) -> None:
    """Report what the upload actually did.

    ``set_values`` can only answer True or False, and "added 142, skipped 8,
    and 12 of them are a type you do not post" is the whole value of the
    screen. The engine calls this right after a successful upload on the
    already-deferred modal interaction.
    """
    detail = await WYRQuestionActions.import_result_text(guild_id)
    if not detail:
        return
    from ..views.base import build_notice_layout
    try:
        await interaction.followup.send(
            view=build_notice_layout("Import finished", detail), ephemeral=True
        )
    except discord.HTTPException as exc:
        logger.warning("Could not deliver the question import summary: %s", exc)


def build_wyr_add_question_node() -> PanelNode:
    """Add one question by hand.

    A stateless one-shot, so it deliberately does NOT set ``counts_as_setting``:
    the bank's "configured" state is reported by the browse node instead, and
    counting both would double-count one thing in the category badge.
    """
    return PanelNode(
        key=ADD_NODE_KEY,
        label="Add a Question",
        kind="action",
        description="Write a question and add it to this server's own bank.",
        on_run=_run_add_question,
    )


def build_wyr_import_node() -> PanelNode:
    """Bulk-import questions from a JSON file.

    ``counts_as_setting=False`` is required, not optional: ``file_upload``
    otherwise infers True, and an import stores no value, so the node would
    read as permanently unconfigured and inflate the category badge forever.
    """
    return PanelNode(
        key=IMPORT_NODE_KEY,
        label="Import Questions",
        kind="file_upload",
        description=(
            "Upload a JSON file to add many questions at once - the fastest way to "
            "fill a new bank.\n\n"
            "**To upload:** Click **Upload JSON** below and attach a `.json` file.\n"
            "**To get the template:** Click **Download Template** for a ready-to-edit "
            "example of all three question types.\n\n"
            "Questions already in your bank are skipped rather than duplicated. "
            "The type of each question is worked out from its shape, so you only need "
            "to set `format` when you want to override that."
        ),
        get_values=WYRQuestionActions.get_import_placeholder,
        set_values=WYRQuestionActions.import_questions,
        schema_validator=validate_wyr_import_schema,
        template_data=build_import_template,
        post_save_hook=_import_post_save,
        counts_as_setting=False,
    )


def build_wyr_question_bank_node() -> PanelNode:
    """Browse this guild's own questions, with delete behind a confirm step.

    Scoped to the guild's own bank by ``list_bank_items`` / ``delete_bank_item``,
    so a server admin can neither see nor delete the shared bank or another
    server's questions.
    """
    return PanelNode(
        key=BANK_NODE_KEY,
        label="Browse and Delete",
        kind="paginated_list",
        description=(
            "Every question this server has added. Deleting one removes it from "
            "your rotation; it does not touch the shared bank."
        ),
        list_get_items=WYRQuestionActions.list_bank_items,
        list_count=WYRQuestionActions.count_bank_items,
        list_format_line=WYRQuestionActions.format_bank_line,
        list_item_value=WYRQuestionActions.bank_item_value,
        list_item_option_label=WYRQuestionActions.bank_item_option_label,
        list_action_label="Delete",
        list_action=WYRQuestionActions.delete_bank_item,
        list_action_confirm_line=WYRQuestionActions.bank_confirm_line,
        list_page_size=10,
        get_values=WYRQuestionActions.bank_summary_values,
        summary_builder=WYRQuestionActions.bank_summary,
        counts_as_setting=True,
    )


WYR_QUESTION_FORMATS_CONFIG = PanelNode(
    key="wyr_question_formats",
    label="Question Types",
    kind="option_select",
    description=(
        "Which kinds of question this server posts. Pick as many as you like.\n\n"
        "🎲 **Would You Rather** - two or three choices to pick between\n"
        "📊 **Question with answers** - any question with up to five answers\n"
        "💬 **Open-ended question** - a prompt with no answers, just discussion\n\n"
        "A question in a type that is switched off stays in your bank unused, so "
        "turn a type on before adding or approving questions of that kind."
    ),
    options=QUESTION_FORMAT_OPTIONS,
    get_values=WYRQuestionActions.get_question_formats,
    set_values=WYRQuestionActions.set_question_formats,
    min_values=1,
    max_values=len(QUESTION_FORMAT_OPTIONS),
)

WYR_QUESTION_SOURCE_CONFIG = PanelNode(
    key="wyr_question_source",
    label="Where Questions Come From",
    kind="option_select",
    description=(
        "Whether daily questions are drawn from the shared bank, this server's own "
        "questions, or both.\n\n"
        "Choosing **Only my own** before you have added any questions means nothing "
        "will be posted until you do."
    ),
    options=QUESTION_SOURCE_OPTIONS,
    get_values=WYRQuestionActions.get_question_source_as_list,
    set_values=WYRQuestionActions.set_question_source_from_list,
    min_values=1,
    max_values=1,
)


#: How many suggestions one member may have waiting at once.
_MAX_PENDING_OPTIONS = [
    ("1", "1"),
    ("2", "2"),
    ("3", "3 (Default)"),
    ("5", "5"),
    ("10", "10"),
]

WYR_REVIEW_CHANNEL_CONFIG = PanelNode(
    key="wyr_review_channel",
    label="Review Channel",
    kind="channel_select",
    description=(
        "Where member suggestions land for a moderator to approve or decline.\n\n"
        "Each suggestion arrives as a post with Approve and Decline buttons. Pick a "
        "staff-only channel: anyone who can see it can read suggestions, though only "
        "your reviewers can act on them."
    ),
    get_values=WYRQuestionActions.get_review_channel_as_list,
    set_values=WYRQuestionActions.set_review_channel,
    clear_values=WYRQuestionActions.clear_review_channel,
    min_values=1,
    max_values=1,
)

WYR_REVIEWER_ROLE_CONFIG = PanelNode(
    key="wyr_reviewer_role",
    label="Who Can Review",
    kind="role_select",
    description=(
        "An extra role allowed to approve or decline suggestions.\n\n"
        "Server administrators and Panel Access roles can always review, so this is "
        "only needed to let someone else help without giving them the whole panel."
    ),
    get_values=WYRQuestionActions.get_reviewer_role_as_list,
    set_values=WYRQuestionActions.set_reviewer_role,
    clear_values=WYRQuestionActions.clear_reviewer_role,
    min_values=1,
    max_values=1,
)

WYR_MAX_PENDING_CONFIG = PanelNode(
    key="wyr_max_pending",
    label="Suggestions Per Member",
    kind="option_select",
    description=(
        "How many suggestions one member can have waiting for review at a time.\n\n"
        "Once they reach the limit they wait for one to be handled before sending "
        "another, so one enthusiastic member cannot fill the queue."
    ),
    options=_MAX_PENDING_OPTIONS,
    get_values=WYRQuestionActions.get_max_pending_as_list,
    set_values=WYRQuestionActions.set_max_pending_from_list,
    min_values=1,
    max_values=1,
)


class _ReviewQueueFlow(PanelFlow):
    """Work through the suggestions waiting for a decision, one at a time.

    Deliberately NOT a ``paginated_list``: that kind supports exactly one
    per-item action behind a confirm step, and a review needs two (approve and
    decline) plus a reason prompt on the decline. So the paging is hand-rolled
    here, the same way the Color Tiers flow does it.

    The decisions themselves route back through the cog's own approve/decline
    handlers - the same code the buttons on a review post use - so the panel and
    the review channel cannot drift into deciding things differently, and the
    atomic claim that stops a double-approve applies to both.
    """

    node_key = QUEUE_NODE_KEY
    audit_section = "wyr"

    def __init__(self, cog, guild, ctx, node):
        super().__init__(cog, guild, ctx, node)
        self._index = 0

    async def _pending(self):
        from Features.daily.wyr_submissions import wyr_submissions
        return await wyr_submissions.list_open(self.guild.id)

    async def open(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._layout())

    async def _layout(self) -> discord.ui.LayoutView:
        from ..views.wyr_question_views import build_review_queue_view
        pending = await self._pending()
        if pending:
            self._index = max(0, min(self._index, len(pending) - 1))
        return build_review_queue_view(
            pending=pending,
            index=self._index,
            guild=self.guild,
            on_prev=self._on_prev,
            on_next=self._on_next,
            on_approve=self._on_approve,
            on_decline=self._on_decline,
            on_back=self._on_back,
            back_label=self.ctx.back_label,
        )

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self._index -= 1
        await self._render(interaction, await self._layout())

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self._index += 1
        await self._render(interaction, await self._layout())

    async def _current(self):
        pending = await self._pending()
        if not pending:
            return None
        self._index = max(0, min(self._index, len(pending) - 1))
        return pending[self._index]

    async def _on_approve(self, interaction: discord.Interaction) -> None:
        submission = await self._current()
        if submission is None:
            await self._refresh_then_notice(
                interaction, "Nothing left",
                "That suggestion is already handled.", await self._layout(),
            )
            return

        cog = interaction.client.get_cog("WYR")
        if cog is None:
            await self._notice(interaction, "Unavailable",
                               "The daily question feature is not loaded right now.")
            return
        # A lightweight stand-in for the review post's view: the handler only
        # reads submission_id and the age-restriction flag off it.
        await cog.handle_submission_approve(
            interaction, _QueueDecision(submission["submission_id"])
        )

    async def _on_decline(self, interaction: discord.Interaction) -> None:
        submission = await self._current()
        if submission is None:
            await self._refresh_then_notice(
                interaction, "Nothing left",
                "That suggestion is already handled.", await self._layout(),
            )
            return

        cog = interaction.client.get_cog("WYR")
        if cog is None:
            await self._notice(interaction, "Unavailable",
                               "The daily question feature is not loaded right now.")
            return
        await cog.handle_submission_reject(
            interaction, _QueueDecision(submission["submission_id"])
        )

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await self._back_to_parent(interaction)


class _QueueDecision:
    """What the cog's approve/decline handlers expect to be handed.

    They accept the review post's persistent view, but only ever read
    ``submission_id`` and ``nsfw`` from it, so the panel passes this instead of
    constructing a message view it has no message for.
    """

    def __init__(self, submission_id: str, nsfw: bool = False):
        self.submission_id = submission_id
        self.nsfw = nsfw


async def _run_review_queue(cog, interaction: discord.Interaction,
                            guild: discord.Guild, ctx: ActionContext) -> None:
    node = build_wyr_review_queue_node()
    await _ReviewQueueFlow(cog, guild, ctx, node).open(interaction)


async def _queue_summary(guild_id: int) -> str:
    """Summary line for the review queue entry.

    A one-shot review screen owns no config, so this reports the workload
    instead - and returns an engine "unset" string when there is none, so the
    category badge does not count an empty queue as a configured setting.
    """
    from Features.daily.wyr_submissions import wyr_submissions
    try:
        waiting = await wyr_submissions.count_open(guild_id)
    except Exception:
        logger.debug("review queue summary failed", exc_info=True)
        return "Empty"
    return f"{waiting} waiting" if waiting else "Empty"


def build_wyr_review_queue_node() -> PanelNode:
    """Review member suggestions from the panel.

    Replaces `/wyr queue`. Stateless as far as configuration goes, so it
    deliberately does not set ``counts_as_setting`` - the Member Suggestions
    toggle above it is the setting.
    """
    return PanelNode(
        key=QUEUE_NODE_KEY,
        label="Review Suggestions",
        kind="action",
        description=(
            "Work through the question suggestions waiting for a decision. "
            "Approving one puts it straight into this server's rotation."
        ),
        summary_builder=_queue_summary,
        on_run=_run_review_queue,
    )


async def _run_post_now(cog, interaction: discord.Interaction,
                        guild: discord.Guild, ctx: ActionContext) -> None:
    """Pick a channel and post a question there straight away.

    Replaces `/wyr post`. A channel picker rather than "wherever you typed",
    which also means you can post somewhere you are not currently looking at.
    """
    from ..views.base import AdminLayoutBuilder, build_notice_layout, readonly_container

    builder = AdminLayoutBuilder()
    builder.add_header("## Post a Question Now")
    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Posts the next question straight away, outside the daily schedule.\n"
        "It counts toward the rotation, so it will not come back tomorrow."
    )))

    async def _on_pick(pi: discord.Interaction):
        if not cog._check_cooldown(pi.user.id, "wyr_post_now", guild.id):
            await pi.response.send_message(
                view=build_notice_layout("Slow Down", "Please wait a moment before trying again."),
                ephemeral=True,
            )
            return

        picked = pi.data.get("values") or []
        channel = guild.get_channel(int(picked[0])) if picked else None
        if channel is None:
            await pi.response.send_message(
                view=build_notice_layout("Channel not found", "Pick a channel I can still see."),
                ephemeral=True,
            )
            return

        wyr_cog = pi.client.get_cog("WYR")
        if wyr_cog is None:
            await pi.response.send_message(
                view=build_notice_layout(
                    "Unavailable", "The daily question feature is not loaded right now."
                ),
                ephemeral=True,
            )
            return

        await pi.response.defer(ephemeral=True)
        ok, message = await wyr_cog.post_question_now(channel)
        await pi.followup.send(
            view=build_notice_layout(
                "Question posted" if ok else "Nothing posted", message
            ),
            ephemeral=True,
        )

    picker = discord.ui.ChannelSelect(
        placeholder="Post a question in...",
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        min_values=1, max_values=1,
    )
    picker.callback = _on_pick
    builder.add_item(discord.ui.ActionRow(picker))

    back = discord.ui.Button(label=ctx.back_label, style=discord.ButtonStyle.secondary)

    async def _on_back(bi: discord.Interaction):
        if ctx.parent_node is not None:
            await cog._navigate_to(
                bi, ctx.parent_node, guild, parent_node=ctx.grandparent_node,
                edit=True, refresh_parent=ctx.refresh_parent, session=ctx.session,
            )
    back.callback = _on_back
    builder.add_item(discord.ui.ActionRow(back))

    await cog._send_or_edit(
        interaction, cog._rebind_session_view(ctx.session, builder.build()), ctx.edit
    )


def build_wyr_post_now_node() -> PanelNode:
    """Post a question on demand. Stateless, so no ``counts_as_setting``."""
    return PanelNode(
        key="wyr_post_now",
        label="Post a Question Now",
        kind="action",
        description="Post the next question to a channel right away, off-schedule.",
        on_run=_run_post_now,
    )


def build_wyr_reset_stats_node() -> PanelNode:
    """Wipe one member's voting record. Replaces `/wyr reset_stats`.

    Uses the engine's member-action factory, which owns the member picker, the
    confirm step and the back navigation - so this only has to say what to run.
    """
    return member_action(
        key="wyr_reset_stats",
        label="Reset Member Stats",
        description=(
            "Clear one member's Would You Rather voting record in this server. "
            "Their record in other servers is untouched, and the questions "
            "themselves are unaffected."
        ),
        placeholder="Select a member to reset...",
        run=WYRQuestionActions.reset_member_stats,
        confirm_text=lambda member: (
            f"Clear **{member.display_name}**'s voting record for this server? "
            f"This cannot be undone."
        ),
        success_text=lambda result, member: (
            f"Cleared {member.mention}'s voting record."
            if result else
            f"{member.mention} had no voting record here."
        ),
    )


def build_wyr_submissions_group() -> PanelNode:
    """Member suggestions, behind one on/off switch.

    A toggle-only-plus-children menu: the toggle is the real setting, and the
    children configure it. Turning it on without a review channel or a reviewer
    role is allowed here but refused at `/wyr submit`, so a member is never told
    their suggestion was sent when nobody can see it.
    """
    return PanelNode(
        key="wyr_submissions",
        label="Member Suggestions",
        kind="menu",
        description=(
            "Let members suggest questions with `/wyr submit`. Each one waits for a "
            "moderator to approve it before it can be posted, and the member gets a "
            "DM either way.\n\n"
            "Set a review channel or a reviewer role before turning this on - "
            "without at least one of them, suggestions are refused rather than "
            "collected where nobody will see them."
        ),
        toggle_get=WYRQuestionActions.get_submissions_enabled,
        toggle_set=WYRQuestionActions.set_submissions_enabled,
        summary_builder=WYRQuestionActions.submissions_summary,
        children={
            "wyr_review_queue": build_wyr_review_queue_node(),
            "wyr_review_channel": WYR_REVIEW_CHANNEL_CONFIG,
            "wyr_reviewer_role": WYR_REVIEWER_ROLE_CONFIG,
            "wyr_max_pending": WYR_MAX_PENDING_CONFIG,
        },
    )


def build_wyr_questions_group() -> PanelNode:
    """The Question Bank sub-menu, mounted as ONE child of WYR Settings.

    One sub-menu rather than five more leaves on the parent: WYR Settings
    already has eight children, and a flat list would crowd the select toward
    Discord's 25-option cap for no benefit.
    """
    return PanelNode(
        key="wyr_questions",
        label="Question Bank",
        kind="menu",
        description=(
            "Add your own questions, import them in bulk, and choose which kinds "
            "this server posts."
        ),
        children={
            "wyr_add_question": build_wyr_add_question_node(),
            "wyr_import_questions": build_wyr_import_node(),
            "wyr_browse_questions": build_wyr_question_bank_node(),
            "wyr_question_formats": WYR_QUESTION_FORMATS_CONFIG,
            "wyr_question_source": WYR_QUESTION_SOURCE_CONFIG,
            "wyr_submissions": build_wyr_submissions_group(),
            "wyr_post_now": build_wyr_post_now_node(),
            "wyr_reset_stats": build_wyr_reset_stats_node(),
        },
    )
