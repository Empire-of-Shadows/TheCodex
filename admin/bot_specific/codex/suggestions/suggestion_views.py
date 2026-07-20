# ---------------------------------------------------------------------------
# VENDORED from admin_engine/ - DO NOT EDIT HERE.
# Edit the master at <repo-root>/admin_engine/ and run:
#     python tools/sync_admin_engine.py
# Drift is enforced by:  python tools/sync_admin_engine.py --check
# ---------------------------------------------------------------------------
"""
Suggestion Config Views using Discord Components v2.

Status view, status-update modal, and export view for the Suggestion admin panel.
The channel select panel is handled by the generic panel engine (panel_configs.py).
"""

from typing import Any, Callable, Awaitable, Dict

import discord

from ....views.base import cid, readonly_container, editable_container

# Display labels for suggestion statuses
_STATUS_LABELS = {
    "pending": "Pending",
    "under_review": "Under Review",
    "approved": "Approved",
    "implemented": "Implemented",
    "rejected": "Rejected",
    "on_hold": "On Hold",
}

# Display order
_STATUS_ORDER = ["pending", "under_review", "approved", "implemented", "rejected", "on_hold"]


def format_suggestion_status(stats: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of the suggestion system as markdown text.

    Consumed by the shared ``info_action`` node (see ``suggestion_nodes.py``),
    which renders the header and Back button around this body.
    """
    channel_id = stats.get("channel_id")
    total_suggestions = stats.get("total_suggestions", 0)
    status_breakdown = stats.get("status_breakdown", {})
    category_breakdown = stats.get("category_breakdown", {})
    top_contributors = stats.get("top_contributors", [])
    total_votes = stats.get("total_votes", 0)

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    sections: list[str] = [
        f"**Server:** {guild.name}\n"
        f"**Channel:** {channel_display}\n"
        f"**Total Suggestions:** {total_suggestions}\n"
        f"**Total Votes Cast:** {total_votes}"
    ]

    if status_breakdown:
        status_lines = []
        for key in _STATUS_ORDER:
            count = status_breakdown.get(key, 0)
            if count:
                status_lines.append(f"**{_STATUS_LABELS.get(key, key)}:** {count}")
        for key, count in status_breakdown.items():
            if key not in _STATUS_LABELS and count:
                status_lines.append(f"**{key.replace('_', ' ').title()}:** {count}")
        if status_lines:
            sections.append("**Status Breakdown**\n" + "\n".join(status_lines))

    if category_breakdown:
        cat_lines = [f"**{cat}:** {count}" for cat, count in category_breakdown.items() if count]
        if cat_lines:
            sections.append("**Category Breakdown**\n" + "\n".join(cat_lines))

    if top_contributors:
        contrib_lines = [
            f"**{c['display_name']}:** {c['count']}"
            for c in top_contributors[:5]
        ]
        sections.append("**Top Contributors**\n" + "\n".join(contrib_lines))

    return "\n\n".join(sections)


class SuggestionStatusUpdateModal(discord.ui.Modal):
    """Modal for admins to update a suggestion's status."""

    ALLOWED_STATUSES = ["Under Review", "Approved", "Implemented", "Rejected", "On Hold"]

    def __init__(
        self,
        callback: Callable[[discord.Interaction, str, str, str], Awaitable[None]],
        *,
        prefill_id: str = "",
        prefill_status: str = "",
        prefill_reason: str = "",
        title: str = "Update Suggestion Status",
    ):
        super().__init__(title=title)
        self._callback = callback

        self.suggestion_id_input = discord.ui.TextInput(
            label="Suggestion ID (first 8 chars)",
            placeholder="e.g. a1b2c3d4",
            min_length=4,
            max_length=36,
            required=True,
            default=prefill_id or None,
        )
        self.status_input = discord.ui.TextInput(
            label="New Status",
            placeholder="Under Review | Approved | Implemented | Rejected | On Hold",
            max_length=30,
            required=True,
            default=prefill_status or None,
        )
        self.reason_input = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Explain the status change",
            max_length=500,
            required=True,
            default=prefill_reason or None,
        )

        self.add_item(self.suggestion_id_input)
        self.add_item(self.status_input)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        sid = self.suggestion_id_input.value.strip()
        status = self.status_input.value.strip()
        reason = self.reason_input.value.strip()

        # Validate status (case-insensitive match)
        matched = None
        for allowed in self.ALLOWED_STATUSES:
            if status.lower() == allowed.lower():
                matched = allowed
                break

        if not matched:
            valid_list = " | ".join(self.ALLOWED_STATUSES)
            # Discord forbids responding to a MODAL_SUBMIT interaction with another
            # modal, so report the validation error as an ephemeral message instead.
            await interaction.response.send_message(
                f"Invalid status. Choose one of: {valid_list}",
                ephemeral=True,
            )
            return

        await self._callback(interaction, sid, matched, reason)


def build_suggestion_export_view(
    export_callback: Callable[[discord.Interaction, str], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build a view with a format selector and export button."""
    layout = discord.ui.LayoutView()

    layout.add_item(discord.ui.TextDisplay("## Export Suggestions"))
    layout.add_item(readonly_container(discord.ui.TextDisplay(
        "Select a format and click **Export**."
    )))

    format_select = discord.ui.Select(
        placeholder="Select export format...",
        custom_id=cid("editor", "select", "suggestion_export_format"),
        options=[
            discord.SelectOption(label="CSV", value="CSV", default=True, description="Comma-separated values"),
            discord.SelectOption(label="JSON", value="JSON", description="JSON file"),
        ],
    )

    selected_format: list[str] = ["CSV"]

    async def on_format_select(interaction: discord.Interaction):
        selected_format[0] = interaction.data["values"][0]
        await interaction.response.defer()

    format_select.callback = on_format_select

    export_btn = discord.ui.Button(
        label="Export",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "export", "suggestion_export"),
    )

    async def on_export(interaction: discord.Interaction):
        await export_callback(interaction, selected_format[0])

    export_btn.callback = on_export

    select_row = discord.ui.ActionRow()
    select_row.add_item(format_select)

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(export_btn)

    layout.add_item(editable_container(select_row, btn_row))

    return layout
