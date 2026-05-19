"""Panel role resolution for TheCodex admin panel.

Mirrors TheHost's role_auth.py but adapts to TheCodex's list-shape
`GuildConfig.roles = {"admin": [ids...], "moderator": [ids...]}`.

Tiers:
  - "admin": guild MANAGE_GUILD OR any role id in cfg.roles["admin"]
  - "mod":   any role id in cfg.roles["moderator"]
  - "none":  no access
"""

from __future__ import annotations

from typing import Literal

import discord

PanelRole = Literal["admin", "mod", "none"]


# Sections a Mod tier may enter. Empty by default - mod opt-in is per section
# as features adopt it. Add a subcategory key here to grant mod access.
MOD_ALLOWED_SECTIONS: frozenset[str] = frozenset()


def get_panel_role(member: discord.Member, cfg) -> PanelRole:
    """Resolve the panel access tier for a member.

    `cfg` is a `storage.config_manager.GuildConfig`.
    """
    if getattr(member, "guild_permissions", None) and member.guild_permissions.manage_guild:
        return "admin"

    admin_ids = set(int(r) for r in (cfg.roles.get("admin") or []))
    mod_ids = set(int(r) for r in (cfg.roles.get("moderator") or []))
    member_role_ids = {r.id for r in getattr(member, "roles", [])}

    if member_role_ids & admin_ids:
        return "admin"
    if member_role_ids & mod_ids:
        return "mod"
    return "none"
