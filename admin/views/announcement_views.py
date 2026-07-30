"""
Announcement Config Views.

Status formatter for the Announcement configuration panel. Every announcement editor is
handled by the generic panel engine (see the announcement nodes in panel_configs.py), so
this module holds only the read-only status body.
"""

from typing import Any, Dict

import discord

# Archive option labels used by the status view
_ARCHIVE_LABELS = {60: "1 Hour", 1440: "1 Day", 4320: "3 Days", 10080: "1 Week"}


def format_announcement_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of announcement configuration as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which renders
    the header and Back button around this body.
    """
    channel_id = overview.get("channel_id")
    thread_auto_create = overview.get("thread_auto_create", True)
    thread_name_format = overview.get("thread_name_format", "")
    archive_duration = overview.get("thread_auto_archive_duration", 1440)
    welcome_message = overview.get("thread_welcome_message", "")
    auto_delete = overview.get("auto_delete_threads", True)

    archive_label = _ARCHIVE_LABELS.get(archive_duration, f"{archive_duration} min")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    welcome_display = f"{welcome_message[:100]}{'...' if len(welcome_message) > 100 else ''}"

    return (
        f"**Server:** {guild.name}\n"
        f"**Channel:** {channel_display}\n"
        f"**Thread Auto-Create:** {'Enabled' if thread_auto_create else 'Disabled'}\n"
        f"**Thread Name Format:** `{thread_name_format}`\n"
        f"**Welcome Message:** {welcome_display}\n"
        f"**Auto-Archive:** {archive_label}\n"
        f"**Auto-Delete Threads:** {'Enabled' if auto_delete else 'Disabled'}"
    )
