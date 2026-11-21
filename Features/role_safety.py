"""Never hand out a role that carries moderator powers (owner ruling 2026-11-20).

Every place TheCodex gives a member a role without an admin choosing that member
goes through here first: guide and info board role buttons, the WYR ping opt-in,
the whitelist role (on join and when staff whitelist someone), and the tag
tracker. A role carrying Administrator, Manage Server, Manage Roles, Manage
Channels, Ban Members or Kick Members is not given out.

The same rule refuses such a role when it is PICKED (admin panel, dashboard
settings, guide and board builder). This second check exists because a role can
gain a permission in Discord long after it was picked. Taking a role away is
never blocked, so members can always drop it.

The list itself is the admin engine's: ``admin/permission_checks.py``
``DANGEROUS_ROLE_PERMISSIONS``.

This module has no ``setup()``, so the cog loader leaves it alone.
"""

from __future__ import annotations

from typing import Optional

import discord

from storage.log import get_logger

logger = get_logger("codex.role_safety")


def _dangerous(role: discord.Role) -> list[str]:
    # Imported here, not at the top: the admin package imports the panel
    # config, which imports the board, which imports this module. A top-level
    # import is a circular import at bot startup.
    from admin.permission_checks import dangerous_role_permissions

    return dangerous_role_permissions(role)


def has_dangerous_permissions(role: discord.Role) -> bool:
    """True when ``role`` carries a permission the bot must not hand out (no log)."""
    return bool(_dangerous(role))


def blocked_role_reason(role: discord.Role) -> Optional[str]:
    """A member-facing refusal when ``role`` must not be handed out, else None."""
    found = _dangerous(role)
    if not found:
        return None
    return (
        f"I can't give you **{role.name}**: it has {', '.join(found)}, and I don't hand "
        f"out roles with those powers. Please let a server admin know."
    )


def is_blocked(role: discord.Role, *, where: str) -> bool:
    """True when ``role`` must not be handed out; logs which feature tried."""
    found = _dangerous(role)
    if not found:
        return False
    logger.warning(
        f"Refused to hand out role {role.name} ({role.id}) in guild {role.guild.id} "
        f"from {where}: it carries {', '.join(found)}"
    )
    return True
