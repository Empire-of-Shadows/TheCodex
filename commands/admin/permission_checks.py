"""
Permission pre-checks for admin panel channel/role configuration.

Validates that the bot has the necessary Discord permissions before saving
a channel or role selection, preventing silent runtime failures.
"""

import discord

# Maps PanelNode key -> list of discord.Permissions attribute names required in that channel.
CHANNEL_PERMISSION_REQUIREMENTS: dict[str, list[str]] = {
    "wyr_channel": ["send_messages", "create_public_threads", "send_messages_in_threads", "embed_links"],
    "nm_welcome_channel": ["send_messages", "embed_links"],
    "ann_channel": ["create_public_threads", "send_messages_in_threads"],
    "sug_channel": ["send_messages", "create_public_threads", "send_messages_in_threads", "embed_links"],
    "guide_channel": ["send_messages"],
    "drops_channel": ["send_messages"],
    "drops_tracker": ["view_channel", "read_message_history"],
    "boost_tracker_channel": ["send_messages"],
}

# Maps PanelNode key -> whether the bot needs manage_roles + hierarchy check.
ROLE_MANAGE_REQUIREMENTS: dict[str, bool] = {
    "nm_whitelist_role": True,
    "tag_tracker_role": True,
}

_PERM_DISPLAY_NAMES: dict[str, str] = {
    "send_messages": "Send Messages",
    "create_public_threads": "Create Public Threads",
    "send_messages_in_threads": "Send Messages in Threads",
    "embed_links": "Embed Links",
    "view_channel": "View Channel",
    "read_message_history": "Read Message History",
}


def check_channel_permissions(guild: discord.Guild, channel_id: int, config_key: str) -> tuple[bool, str | None]:
    """Check if the bot has required permissions in the given channel.

    Returns (True, None) if OK, or (False, error_message) if permissions are missing.
    """
    required = CHANNEL_PERMISSION_REQUIREMENTS.get(config_key)
    if not required:
        return True, None

    channel = guild.get_channel(channel_id)
    if channel is None:
        return False, "Could not find that channel. It may have been deleted."

    perms = channel.permissions_for(guild.me)
    missing = [name for name in required if not getattr(perms, name, False)]

    if not missing:
        return True, None

    missing_display = ", ".join(f"**{_PERM_DISPLAY_NAMES.get(p, p)}**" for p in missing)
    return False, (
        f"The bot is missing permissions in <#{channel_id}>:\n"
        f"{missing_display}\n\n"
        f"Grant these permissions to the bot in that channel's settings, then try again."
    )


def check_role_permissions(guild: discord.Guild, role_id: int, config_key: str) -> tuple[bool, str | None]:
    """Check if the bot can manage the given role (manage_roles perm + hierarchy).

    Returns (True, None) if OK, or (False, error_message) if the bot cannot manage the role.
    """
    if not ROLE_MANAGE_REQUIREMENTS.get(config_key):
        return True, None

    if not guild.me.guild_permissions.manage_roles:
        return False, (
            "The bot is missing the **Manage Roles** server permission.\n\n"
            "Grant it in Server Settings > Roles, then try again."
        )

    role = guild.get_role(role_id)
    if role is None:
        return False, "Could not find that role. It may have been deleted."

    if role >= guild.me.top_role:
        bot_role = guild.me.top_role
        return False, (
            f"The bot's highest role must be **above** **@{role.name}** in the role hierarchy.\n\n"
            f"**@{role.name}** is at position {role.position}, but the bot's top role "
            f"(**@{bot_role.name}**) is at position {bot_role.position}.\n"
            f"Move the bot's role higher in Server Settings > Roles."
        )

    return True, None
