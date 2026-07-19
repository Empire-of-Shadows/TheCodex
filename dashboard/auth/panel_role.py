"""Panel-role resolution for the Codex dashboard.

The web-side counterpart of the Discord panel's tier resolution (the engine's
`auth.resolve_panel_role_from_config`). TheCodex stores admin and moderator roles as lists in
`GuildConfig.roles = {"admin_role_ids": [...], "mod_role_ids": [...]}`, so resolution checks
set overlap rather than a single id.

Tiers:
  - "admin": MANAGE_GUILD OR overlap with cfg.roles["admin_role_ids"]
  - "mod":   overlap with cfg.roles["mod_role_ids"]
  - "none":  no access
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import httpx
from fastapi import Depends, HTTPException

from dashboard import db
from dashboard.auth.dependencies import get_current_user
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE, MANAGE_GUILD_PERMISSION
from storage.log import get_logger

logger = get_logger("dashboard.auth.panel_role")

PanelRole = Literal["admin", "mod", "none"]

_MEMBER_CACHE_TTL = 60.0
_MEMBER_NEGATIVE_TTL = 60.0
_member_cache: dict[tuple[str, str], tuple[frozenset[str], float]] = {}
_cache_lock = asyncio.Lock()

# Token-bucket rate limiter for the bot-token member-fetch path (mirrors
# TheHost). Discord's global bot limit is 50/s; stay well under to leave
# headroom for the channels/roles/guilds fetches that share the token. Both
# /api/me and /api/guilds probe panel roles, so a user in many configured
# guilds could otherwise burst member fetches.
_RATE_CAPACITY = 5         # burst
_RATE_REFILL_PER_SEC = 20.0
_rate_tokens = float(_RATE_CAPACITY)
_rate_last_refill = time.monotonic()
_rate_lock = asyncio.Lock()


async def _acquire_rate_slot() -> None:
    """Block until the internal token bucket releases a slot."""
    global _rate_tokens, _rate_last_refill
    while True:
        async with _rate_lock:
            now = time.monotonic()
            elapsed = now - _rate_last_refill
            if elapsed > 0:
                _rate_tokens = min(
                    float(_RATE_CAPACITY),
                    _rate_tokens + elapsed * _RATE_REFILL_PER_SEC,
                )
                _rate_last_refill = now
            if _rate_tokens >= 1.0:
                _rate_tokens -= 1.0
                return
            need = 1.0 - _rate_tokens
            wait = need / _RATE_REFILL_PER_SEC
        await asyncio.sleep(wait)


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

    await _acquire_rate_slot()

    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 429:
                retry = float(resp.headers.get("Retry-After", "2"))
                await asyncio.sleep(retry)
                await _acquire_rate_slot()
                resp = await client.get(url, headers=headers)
    except Exception as e:
        logger.warning("Discord member fetch failed for %s/%s: %s", guild_id, user_id, e)
        return frozenset()

    if resp.status_code == 404:
        # User not a member - cache the empty result for the full TTL.
        roles: frozenset[str] = frozenset()
    elif resp.status_code == 200:
        roles = frozenset(str(r) for r in resp.json().get("roles", []))
    else:
        logger.warning("Discord member fetch %s/%s -> %s", guild_id, user_id, resp.status_code)
        # Cache unexpected failures only for the shorter negative TTL so they
        # clear quickly rather than sticking for the full window.
        async with _cache_lock:
            _member_cache[key] = (frozenset(), now - (_MEMBER_CACHE_TTL - _MEMBER_NEGATIVE_TTL))
        return frozenset()

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
    # Canonical keys are admin_role_ids / mod_role_ids; fall back to the legacy
    # admin / moderator names for documents not yet migrated.
    admin_ids = frozenset(
        str(r) for r in (roles.get("admin_role_ids") or roles.get("admin") or [])
    )
    mod_ids = frozenset(
        str(r) for r in (roles.get("mod_role_ids") or roles.get("moderator") or [])
    )
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


async def require_guild_admin(
    guild_id: str,
    session: dict = Depends(get_current_user),
) -> dict:
    """FastAPI dependency: 401 if anon, 403 unless the user resolves to the
    "admin" tier for the guild. Returns the session.

    This is the live equivalent of the old session-only MANAGE_GUILD check: a
    configured admin role is verified against Discord via the bot token, so the
    builder enforces the same authority the settings route does. (A MANAGE_GUILD
    holder is still recognised from the session — the app has no stored OAuth
    token to re-derive that permission live — but this closes the gap for
    role-based admins and keeps the two write surfaces consistent.)
    """
    role = await resolve_panel_role(session, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required for this guild")
    return session
