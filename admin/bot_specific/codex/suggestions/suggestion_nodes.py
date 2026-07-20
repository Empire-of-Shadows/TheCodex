# ---------------------------------------------------------------------------
# VENDORED from admin_engine/ - DO NOT EDIT HERE.
# Edit the master at <repo-root>/admin_engine/ and run:
#     python tools/sync_admin_engine.py
# Drift is enforced by:  python tools/sync_admin_engine.py --check
# ---------------------------------------------------------------------------
"""
Suggestion admin-panel nodes.

These PanelNode factories wire the Suggestions admin group (Update Status / Export /
View Status) to a bot's suggestion backend. This is a **per-bot feature**: it depends on
the bot's ``suggestions_*`` collections and the ``/suggest`` feature, so it is only active
in bots that reference these nodes from their ``panel_configs.py``. The code lives in the
shared admin engine under ``admin_engine/bot_specific/codex/suggestions/``, vendored into
TheCodex alone.

They follow the same shape as the factories in ``actions/structure/modals.py``
(``modal_action``) and ``actions/structure/info.py`` (``info_action``): render into message-2
via ``cog._send_or_edit``, chain Back-navigation through ``cog._navigate_to``, and gate repeat
submissions with ``cog._check_cooldown``. The generic ``modal_action`` factory only supports a
single-field modal, so the Update Status node opens the multi-field ``SuggestionStatusUpdateModal``
directly.
"""

from __future__ import annotations

import discord

from ....views.panel_engine import PanelNode, ActionContext
from ....views.base import AdminLayoutBuilder, build_notice_layout, cid, readonly_container, editable_container
from ....actions.structure import info_action
from .suggestion_views import (
    SuggestionStatusUpdateModal,
    build_suggestion_export_view,
    format_suggestion_status,
)
from .suggestion_actions import SuggestionActions


def _make_back_button(cog, guild, ctx: ActionContext, node_key: str) -> discord.ui.ActionRow:
    """A Back button that returns to the parent menu (mirrors the vendored factories)."""

    async def _back(ci: discord.Interaction):
        if ctx.parent_node is not None:
            await cog._navigate_to(
                ci, ctx.parent_node, guild, parent_node=ctx.grandparent_node,
                edit=True, refresh_parent=ctx.refresh_parent, session=ctx.session,
            )
        else:
            await ci.response.edit_message(view=AdminLayoutBuilder().add_text("Closed.").build())

    back_btn = discord.ui.Button(
        label=ctx.back_label or "Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("suggestion", "back", node_key),
    )
    back_btn.callback = _back
    row = discord.ui.ActionRow()
    row.add_item(back_btn)
    return row


def build_suggestion_update_status_node() -> PanelNode:
    """An ``action`` node that opens the multi-field status-update modal."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext):
        builder = AdminLayoutBuilder()
        builder.add_header("## Update Suggestion Status")
        builder.add_item(readonly_container(discord.ui.TextDisplay(
            "Change a suggestion's review status. You'll need the suggestion's ID "
            "(the first 8 characters shown on the suggestion post)."
        )))

        btn = discord.ui.Button(
            label="Update Status",
            style=discord.ButtonStyle.primary,
            custom_id=cid("suggestion", "open", "sug_update_status"),
        )

        async def _open(bi: discord.Interaction):
            async def _submit(mi: discord.Interaction, sid: str, status: str, reason: str):
                if not cog._check_cooldown(mi.user.id, "sug_update_status"):
                    await mi.response.send_message(
                        view=build_notice_layout("Slow Down", "Please wait a moment before trying again."),
                        ephemeral=True,
                    )
                    return
                await mi.response.defer(ephemeral=True)
                result = await SuggestionActions.update_suggestion_status(
                    guild.id, sid, status, admin_id=mi.user.id, reason=reason, bot=cog.bot,
                )
                title = "Status Updated" if result.get("success") else "Update Failed"
                await mi.followup.send(
                    view=build_notice_layout(title, result.get("message", "Done.")),
                    ephemeral=True,
                )
                if result.get("success") and ctx.refresh_parent:
                    await ctx.refresh_parent()

            await bi.response.send_modal(SuggestionStatusUpdateModal(callback=_submit))

        btn.callback = _open
        open_row = discord.ui.ActionRow()
        open_row.add_item(btn)
        builder.add_item(editable_container(open_row))
        builder.add_item(_make_back_button(cog, guild, ctx, "sug_update_status"))

        await cog._send_or_edit(interaction, builder.build(), ctx.edit)

    return PanelNode(
        key="sug_update_status",
        label="Update Status",
        kind="action",
        description="Update a suggestion's review status.",
        on_run=_on_run,
        mod_allowed=False,
    )


def build_suggestion_export_node() -> PanelNode:
    """An ``action`` node that exports suggestions as CSV or JSON."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext):
        async def _export(ei: discord.Interaction, format_type: str):
            result = await SuggestionActions.export_suggestions(guild.id, format_type)
            if result is None:
                await ei.response.send_message(
                    view=build_notice_layout("Nothing to Export", "There are no suggestions to export yet."),
                    ephemeral=True,
                )
                return
            file, count = result
            await ei.response.send_message(
                content=f"Exported {count} suggestion(s) as {format_type}.",
                file=file,
                ephemeral=True,
            )

        view = build_suggestion_export_view(_export)
        view.add_item(_make_back_button(cog, guild, ctx, "sug_export"))

        await cog._send_or_edit(interaction, view, ctx.edit)

    return PanelNode(
        key="sug_export",
        label="Export",
        kind="action",
        description="Export suggestions as CSV or JSON.",
        on_run=_on_run,
        mod_allowed=False,
    )


def build_suggestion_status_node() -> PanelNode:
    """A read-only ``action`` node showing suggestion-system stats (via the shared info_action)."""

    async def _render(cog, guild, ctx) -> str:
        stats = await SuggestionActions.get_overview(guild.id, cog.bot)
        return format_suggestion_status(stats, guild)

    return info_action(
        key="sug_status",
        label="View Status",
        description="View suggestion system stats.",
        render=_render,
        mod_allowed=True,
    )
