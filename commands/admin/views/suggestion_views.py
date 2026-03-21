"""
Suggestion Config Views using Discord Components v2.

Status view, status-update modal, and export view for the Suggestion admin panel.
The channel select panel is handled by the generic panel engine (panel_configs.py).
"""

from typing import Any, Callable, Awaitable, Dict

import discord

from .base import AdminLayoutBuilder, create_unique_id

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


def build_suggestion_status_view(stats: Dict[str, Any], guild: discord.Guild) -> discord.ui.LayoutView:
    """Build a read-only status overview of the suggestion system."""
    builder = AdminLayoutBuilder()

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

    builder.add_header("## Suggestion System Status")
    builder.add_text(f"**Server:** {guild.name}")
    builder.add_separator()

    # Channel and totals
    builder.add_text(
        f"**Channel:** {channel_display}\n"
        f"**Total Suggestions:** {total_suggestions}\n"
        f"**Total Votes Cast:** {total_votes}"
    )

    # Status breakdown
    if status_breakdown:
        builder.add_separator()
        lines = []
        for key in _STATUS_ORDER:
            count = status_breakdown.get(key, 0)
            if count:
                lines.append(f"**{_STATUS_LABELS.get(key, key)}:** {count}")
        # Include any statuses not in our predefined list
        for key, count in status_breakdown.items():
            if key not in _STATUS_LABELS and count:
                lines.append(f"**{key.replace('_', ' ').title()}:** {count}")

        if lines:
            builder.add_text("**Status Breakdown**\n" + "\n".join(lines))

    # Category breakdown
    if category_breakdown:
        builder.add_separator()
        cat_lines = [f"**{cat}:** {count}" for cat, count in category_breakdown.items() if count]
        if cat_lines:
            builder.add_text("**Category Breakdown**\n" + "\n".join(cat_lines))

    # Top contributors
    if top_contributors:
        builder.add_separator()
        contrib_lines = [
            f"**{c['display_name']}:** {c['count']}"
            for c in top_contributors[:5]
        ]
        builder.add_text("**Top Contributors**\n" + "\n".join(contrib_lines))

    return builder.build()


class SuggestionStatusUpdateModal(discord.ui.Modal):
    """Modal for admins to update a suggestion's status."""

    ALLOWED_STATUSES = ["Under Review", "Approved", "Implemented", "Rejected", "On Hold"]

    def __init__(
        self,
        callback: Callable[[discord.Interaction, str, str, str], Awaitable[None]],
    ):
        super().__init__(title="Update Suggestion Status")
        self._callback = callback

        self.suggestion_id_input = discord.ui.TextInput(
            label="Suggestion ID (first 8 chars)",
            placeholder="e.g. a1b2c3d4",
            min_length=4,
            max_length=36,
            required=True,
        )
        self.status_input = discord.ui.TextInput(
            label="New Status",
            placeholder="Under Review | Approved | Implemented | Rejected | On Hold",
            max_length=30,
            required=True,
        )
        self.reason_input = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Explain the status change",
            max_length=500,
            required=True,
        )

        self.add_item(self.suggestion_id_input)
        self.add_item(self.status_input)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        status = self.status_input.value.strip()

        # Validate status (case-insensitive match)
        matched = None
        for allowed in self.ALLOWED_STATUSES:
            if status.lower() == allowed.lower():
                matched = allowed
                break

        if not matched:
            valid_list = ", ".join(self.ALLOWED_STATUSES)
            await interaction.response.send_message(
                f"Invalid status `{status}`. Valid options: {valid_list}",
                ephemeral=True,
            )
            return

        await self._callback(
            interaction,
            self.suggestion_id_input.value.strip(),
            matched,
            self.reason_input.value.strip(),
        )


def build_suggestion_export_view(
    export_callback: Callable[[discord.Interaction, str], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build a view with a format selector and export button."""
    unique_id = create_unique_id()
    layout = discord.ui.LayoutView(timeout=300.0)

    layout.add_item(discord.ui.TextDisplay("## Export Suggestions"))
    layout.add_item(discord.ui.TextDisplay("Select a format and click **Export**."))
    layout.add_item(discord.ui.Separator())

    format_select = discord.ui.Select(
        placeholder="Select export format...",
        custom_id=f"sug_export_fmt_{unique_id}",
        options=[
            discord.SelectOption(label="CSV", value="CSV", description="Comma-separated values"),
            discord.SelectOption(label="JSON", value="JSON", description="JSON file"),
        ],
    )

    # Track selected format
    selected_format: list[str] = ["CSV"]

    async def on_format_select(interaction: discord.Interaction):
        selected_format[0] = interaction.data["values"][0]
        await interaction.response.defer()

    format_select.callback = on_format_select

    select_row = discord.ui.ActionRow()
    select_row.add_item(format_select)
    layout.add_item(select_row)

    export_btn = discord.ui.Button(
        label="Export",
        style=discord.ButtonStyle.primary,
        custom_id=f"sug_export_btn_{unique_id}",
    )

    async def on_export(interaction: discord.Interaction):
        await export_callback(interaction, selected_format[0])

    export_btn.callback = on_export

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(export_btn)
    layout.add_item(btn_row)

    return layout
