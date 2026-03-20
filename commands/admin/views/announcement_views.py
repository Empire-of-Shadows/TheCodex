"""
Announcement Config Views using Discord Components v2.

Status view for the Announcement configuration panel.
All other Announcement panels are handled by the generic panel engine (panel_configs.py).
"""

from typing import Dict, Any

import discord

from .base import AdminLayoutBuilder

# Archive option labels used by the status view
_ARCHIVE_LABELS = {60: "1 Hour", 1440: "1 Day", 4320: "3 Days", 10080: "1 Week"}


def build_announcement_status_view(stats: Dict[str, Any], guild: discord.Guild) -> discord.ui.LayoutView:
    """Build a read-only status overview of announcement configuration."""
    builder = AdminLayoutBuilder()

    channel_id = stats.get("channel_id")
    thread_auto_create = stats.get("thread_auto_create", True)
    thread_name_format = stats.get("thread_name_format", "")
    archive_duration = stats.get("thread_auto_archive_duration", 1440)
    welcome_message = stats.get("thread_welcome_message", "")
    auto_delete = stats.get("auto_delete_threads", True)

    archive_label = _ARCHIVE_LABELS.get(archive_duration, f"{archive_duration} min")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    builder.add_header("## Announcement Configuration Status")
    builder.add_text(f"**Server:** {guild.name}")
    builder.add_separator()

    builder.add_text(
        f"**Channel:** {channel_display}\n"
        f"**Thread Auto-Create:** {'Enabled' if thread_auto_create else 'Disabled'}\n"
        f"**Thread Name Format:** `{thread_name_format}`\n"
        f"**Welcome Message:** {welcome_message[:100]}{'...' if len(welcome_message) > 100 else ''}\n"
        f"**Auto-Archive:** {archive_label}\n"
        f"**Auto-Delete Threads:** {'Enabled' if auto_delete else 'Disabled'}"
    )

    return builder.build()
