"""
New Member Config Views.

Status formatter for the New Members configuration panel. Every New Members editor is
handled by the generic panel engine (see the new-member nodes in panel_configs.py), so
this module holds only the read-only status body.
"""

from typing import Any, Dict

import discord


def format_new_member_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of New Members configuration as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which
    renders the header and Back button around this body.
    """
    age = overview.get("account_age_requirement_days", 90)
    auto_kick = overview.get("auto_kick_new_accounts", True)
    greeting_enabled = overview.get("greeting_enabled", True)
    whitelist_enabled = overview.get("whitelist_enabled", True)
    whitelist_role_id = overview.get("whitelist_role_id")
    greeting_channel_id = overview.get("greeting_channel_id")
    stats = overview.get("whitelist_stats", {})

    # Greeting channel display
    if greeting_channel_id:
        greeting_ch = guild.get_channel(greeting_channel_id)
        greeting_display = greeting_ch.mention if greeting_ch else f"Not found ({greeting_channel_id})"
    else:
        greeting_display = "Not configured"

    # Whitelist role display
    if whitelist_role_id:
        role = guild.get_role(whitelist_role_id)
        role_display = role.mention if role else f"Not found ({whitelist_role_id})"
    else:
        role_display = "Not configured"

    return (
        f"**Server:** {guild.name}\n"
        f"**Account Age Requirement:** {age} days\n"
        f"**Auto-Kick New Accounts:** {'Enabled' if auto_kick else 'Disabled'}\n"
        f"**Greeting Messages:** {'Enabled' if greeting_enabled else 'Disabled'}\n"
        f"**Greeting Channel:** {greeting_display}\n"
        f"**Whitelist System:** {'Enabled' if whitelist_enabled else 'Disabled'}\n"
        f"**Whitelist Role:** {role_display}\n\n"
        f"**Whitelist Stats:**\n"
        f"- Active entries: {stats.get('active', 0)}\n"
        f"- Inactive entries: {stats.get('inactive', 0)}\n"
        f"- Total entries: {stats.get('total', 0)}\n"
        f"- Roles currently assigned: {stats.get('role_assigned', 0)}"
    )
