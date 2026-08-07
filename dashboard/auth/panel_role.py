"""Panel-role policy for the Codex dashboard (2-tier: admin / none).

The live guild-permission plumbing (bot-token MANAGE_GUILD check, member-role fetch, rate
limiter, caches) lives in the shared engine at ``dashboard/_engine/auth/panel_access.py``.
This file is only codex's tier policy: TheCodex stores the panel-access roles as a list at
``GuildConfig.roles.admin_role_ids``, so resolution checks set overlap. Web-side counterpart
of the engine's ``auth.resolve_panel_role_from_config``.

Codex's admin surface is admin-only: there is no Mod tier on the bot side, so this seam
never resolves one either. A stale ``roles.mod_role_ids`` value in an old document grants
nothing.

Tiers:
  - "admin": MANAGE_GUILD (verified live via the bot token) OR overlap with
    roles.admin_role_ids
  - "none":  no panel access
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from dashboard import db
from dashboard._engine.auth.panel_access import (
    PanelRole,
    has_manage_guild,
    member_role_ids,
    session_has_manage_guild,
)
from dashboard.auth.dependencies import get_current_user


async def _guild_admin_roles(guild_id: str) -> frozenset[str]:
    """Return the admin_role_ids configured for the guild."""
    try:
        # Validate as a snowflake, query by the canonical string form (the
        # GuildConfig collection is string-keyed since migration m4).
        gid = str(int(guild_id))
    except (TypeError, ValueError):
        return frozenset()
    doc = await db.guild_config().find_one({"guild_id": gid}, projection={"roles": 1})
    if not doc:
        return frozenset()
    roles = doc.get("roles") or {}
    # Canonical key is admin_role_ids; fall back to the legacy admin name for
    # documents not yet migrated.
    return frozenset(
        str(r) for r in (roles.get("admin_role_ids") or roles.get("admin") or [])
    )


async def resolve_panel_role(
    session: dict, guild_id: str, *, verify_manage_live: bool = True
) -> PanelRole:
    """Resolve the user's panel tier for `guild_id` - "admin" or "none".

    ``verify_manage_live=False`` uses the cheap session snapshot for the MANAGE_GUILD step
    (for guild-list probing); the default verifies it live via the bot token.
    """
    if verify_manage_live:
        if await has_manage_guild(session, guild_id):
            return "admin"
    elif session_has_manage_guild(session, guild_id):
        return "admin"

    admin_ids = await _guild_admin_roles(guild_id)
    if not admin_ids:
        return "none"

    user_id = session.get("user_id") or session.get("user_data", {}).get("id")
    if not user_id:
        return "none"

    member_roles = await member_role_ids(str(guild_id), str(user_id))
    if not member_roles:
        return "none"

    if member_roles & admin_ids:
        return "admin"
    return "none"


async def require_panel_access(session: dict, guild_id: str) -> PanelRole:
    role = await resolve_panel_role(session, guild_id)
    if role == "none":
        raise HTTPException(status_code=403, detail="No panel access for this guild")
    return role


async def require_guild_admin(
    guild_id: str,
    session: dict = Depends(get_current_user),
) -> dict:
    """FastAPI dependency: 401 if anon, 403 unless the user resolves to the "admin" tier
    for the guild (verified live via the bot token). Returns the session."""
    role = await resolve_panel_role(session, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required for this guild")
    return session
