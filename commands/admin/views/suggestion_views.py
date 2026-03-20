"""
Suggestion Config Views using Discord Components v2.

Status view for the Suggestion configuration panel.
The channel select panel is handled by the generic panel engine (panel_configs.py).
"""

from typing import Dict, Any

import discord

from .base import AdminLayoutBuilder

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

    return builder.build()
