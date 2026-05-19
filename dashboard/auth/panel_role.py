"""Panel-role resolution for the Codex dashboard.

Mirrors `commands/admin/role_auth.py` for the web side. TheCodex stores admin
and moderator roles as lists in `GuildConfig.roles = {"admin": [...], "moderator": [...]}`,
so resolution checks set overlap rather than a single id.

Tiers:
  - "admin": MANAGE_GUILD OR overlap with cfg.roles["admin"]
  - "mod":   overlap with cfg.roles["moderator"]
  - "none":  no access
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

import httpx
from fastapi import HTTPException

from dashboard import db
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE, MANAGE_GUILD_PERMISSION

logger = logging.getLogger(__name__)

PanelRole = Literal["admin", "mod", "none"]

_MEMBER_CACHE_TTL = 60.0
_member_cache: dict[tuple[str, str], tuple[frozenset[str], float]] = {}
_cache_lock = asyncio.Lock()


def _session_has_manage_guild(session: dict, guild_id: str) -> bool:
    for g in session.get("guilds", []):
        if str(g["id"]) == str(guild_id):
            perms = int(g.get("permissions", 0))
            return (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION
    return False


async def _member_role_ids(guild_id: str, user_id: str) -> frozenset[str]:
    key = (str(guild_id), str(user_id))
    now = time.monotonic()
    cached = _member_cache.get(key)
    if cached is not None and now - cached[1] < _MEMBER_CACHE_TTL:
        return cached[0]

    if not BOT_TOKEN:
        return frozenset()

    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except Exception as e:
        logger.warning("Discord member fetch failed for %s/%s: %s", guild_id, user_id, e)
        return frozenset()

    if resp.status_code == 200:
        roles = frozenset(str(r) for r in resp.json().get("roles", []))
    else:
        roles = frozenset()

    async with _cache_lock:
        _member_cache[key] = (roles, now)
    return roles


async def _guild_role_lists(guild_id: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return (admin_role_ids, mod_role_ids) configured for the guild."""
    try:
        gid = int(guild_id)
    except (TypeError, ValueError):
        return (frozenset(), frozenset())
    doc = await db.guild_config().find_one({"guild_id": gid}, projection={"roles": 1})
    if not doc:
        return (frozenset(), frozenset())
    roles = doc.get("roles") or {}
    admin_ids = frozenset(str(r) for r in (roles.get("admin") or []))
    mod_ids = frozenset(str(r) for r in (roles.get("moderator") or []))
    return (admin_ids, mod_ids)


async def resolve_panel_role(session: dict, guild_id: str) -> PanelRole:
    if _session_has_manage_guild(session, guild_id):
        return "admin"

    admin_ids, mod_ids = await _guild_role_lists(guild_id)
    if not admin_ids and not mod_ids:
        return "none"

    user_id = session.get("user_id") or session.get("user_data", {}).get("id")
    if not user_id:
        return "none"

    member_roles = await _member_role_ids(str(guild_id), str(user_id))
    if not member_roles:
        return "none"

    if member_roles & admin_ids:
        return "admin"
    if member_roles & mod_ids:
        return "mod"
    return "none"


async def require_panel_access(session: dict, guild_id: str) -> PanelRole:
    role = await resolve_panel_role(session, guild_id)
    if role == "none":
        raise HTTPException(status_code=403, detail="No panel access for this guild")
    return role
