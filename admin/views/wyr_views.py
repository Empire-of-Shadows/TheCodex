"""
WYR Config Views.

Status formatter for the WYR configuration panel. Every WYR editor is handled by the
generic panel engine (see the WYR nodes in panel_configs.py), so this module holds only
the read-only status body.
"""

from typing import Any, Dict

import discord

# Archive option labels used by the status view
_ARCHIVE_LABELS = {60: "1 Hour", 1440: "1 Day", 4320: "3 Days", 10080: "1 Week"}


def format_wyr_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of WYR configuration as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which renders
    the header and Back button around this body.
    """
    channel_id = overview.get("wyr_channel_id")
    ping_role_id = overview.get("wyr_ping_role_id")
    hour = overview.get("hour", 6)
    minute = overview.get("minute", 0)
    tz = overview.get("timezone", "America/Chicago")
    category = overview.get("default_category", "sfw")
    name_fmt = overview.get("thread_name_format", "")
    starter = overview.get("thread_starter_message", "")
    archive = overview.get("thread_auto_archive", 1440)
    cleanup = overview.get("mapping_cleanup_days", 30)
    prompt_enabled = overview.get("subscribe_prompt_enabled", True)

    archive_label = _ARCHIVE_LABELS.get(archive, f"{archive} min")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    if ping_role_id:
        role = guild.get_role(ping_role_id)
        ping_display = role.mention if role else f"Not found ({ping_role_id})"
    else:
        ping_display = "Not configured"

    starter_display = f"{starter[:100]}{'...' if len(starter) > 100 else ''}"

    body = (
        f"**Server:** {guild.name}\n"
        f"**Channel:** {channel_display}\n"
        f"**Ping Role:** {ping_display}\n"
        f"**Notification Offer:** {'Enabled' if prompt_enabled else 'Disabled'}\n"
        f"**Post Time:** {hour:02d}:{minute:02d} ({tz})\n"
        f"**Default Category:** {category}\n"
        f"**Thread Name Format:** `{name_fmt}`\n"
        f"**Starter Message:** {starter_display}\n"
        f"**Auto-Archive:** {archive_label}\n"
        f"**Mapping Cleanup:** {cleanup} days"
    )

    # The question-content block, when the overview carries it. Without this,
    # View Status silently omits the settings that decide whether anything gets
    # posted at all - which is worse than not having the screen.
    questions = overview.get("questions")
    if questions:
        from .wyr_question_views import format_question_bank_status
        body += "\n\n" + format_question_bank_status(questions)

    return body
