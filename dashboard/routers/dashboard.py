"""Dashboard API routes — user info and guild listing."""

import asyncio
import time
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, HTTPException

from dashboard.auth.dependencies import get_current_user, require_guild_manage
from dashboard.auth.panel_role import resolve_panel_role
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE, MANAGE_GUILD_PERMISSION
from dashboard import db
from storage.log import get_logger

logger = get_logger("dashboard.routers.dashboard")

router = APIRouter(tags=["dashboard"])

_DISCORD_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Simple TTL caches for Discord API results to avoid 429s.
_bot_guilds_cache: dict[str, object] = {"ids": set(), "ts": 0.0}
_bot_id_cache: dict[str, object] = {"id": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 minutes

# Per-resource async locks so concurrent requests share one Discord fetch.
_bot_guilds_lock = asyncio.Lock()
_bot_id_lock = asyncio.Lock()
_channels_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_roles_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


_ADMIN_PROBE_LIMIT = 25


@router.get("/me")
async def me(session: dict = Depends(get_current_user)):
    """Return the current user's info plus panel-access flags.

    Mirrors TheHost: probe configured panel roles across bot-present session
    guilds. admin = MANAGE_GUILD anywhere OR an admin role anywhere; mod = a mod
    role anywhere (`resolve_panel_role` only returns "mod" when the user is not
    admin on that guild, so MANAGE_GUILD never grants mod).
    """
    user = session["user_data"]
    can_manage_any = any(
        (int(g.get("permissions", 0)) & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION
        for g in session.get("guilds", [])
    )

    bot_guild_ids = await _fetch_bot_guild_ids()
    candidate_ids = [
        g["id"] for g in session.get("guilds", []) if g["id"] in bot_guild_ids
    ][:_ADMIN_PROBE_LIMIT]
    results = await asyncio.gather(
        *(resolve_panel_role(session, gid) for gid in candidate_ids),
        return_exceptions=True,
    )
    roles = [r for r in results if isinstance(r, str)]
    can_access_admin_any = can_manage_any or any(r == "admin" for r in roles)
    can_access_mod_any = any(r == "mod" for r in roles)

    return {
        "id": user["id"],
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
        "discriminator": user.get("discriminator"),
        "can_access_admin_any": can_access_admin_any,
        "can_access_mod_any": can_access_mod_any,
        "can_access_settings_any": can_access_admin_any or can_access_mod_any,
    }


async def _fetch_bot_guild_ids() -> set[str]:
    """Fetch the set of guild IDs the bot is currently in (cached, single-flight)."""
    if not BOT_TOKEN:
        return set()

    now = time.monotonic()
    if _bot_guilds_cache["ids"] and now - _bot_guilds_cache["ts"] < _CACHE_TTL:
        return _bot_guilds_cache["ids"]

    async with _bot_guilds_lock:
        # Double-check after acquiring lock.
        now = time.monotonic()
        if _bot_guilds_cache["ids"] and now - _bot_guilds_cache["ts"] < _CACHE_TTL:
            return _bot_guilds_cache["ids"]

        guild_ids: set[str] = set()
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        after = "0"

        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
            while True:
                url = f"{DISCORD_API_BASE}/users/@me/guilds?limit=200&after={after}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                    logger.info("Bot guilds rate-limited, retrying in %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning("Failed to fetch bot guilds: %s", resp.status_code)
                    return _bot_guilds_cache["ids"] or guild_ids
                guilds = resp.json()

                if not guilds:
                    break

                for g in guilds:
                    guild_ids.add(g["id"])

                if len(guilds) < 200:
                    break
                after = guilds[-1]["id"]

        _bot_guilds_cache["ids"] = guild_ids
        _bot_guilds_cache["ts"] = now
        return guild_ids


async def _guild_ids_with_config(guild_ids: list[str]) -> set[str]:
    """Return which of the given guild IDs have an existing guild config doc."""
    if not guild_ids:
        return set()

    cursor = db.guild_config().find(
        {"guild_id": {"$in": [int(gid) for gid in guild_ids]}},
        {"guild_id": 1},
    )
    return {str(doc["guild_id"]) async for doc in cursor}


@router.get("/guilds")
async def guilds(session: dict = Depends(get_current_user)):
    """Return guilds the user can manage as admin or mod, with bot status + role.

    Includes every session guild where the user holds MANAGE_GUILD (admin, shown
    even when the bot is absent so they can invite it) or a configured admin/mod
    role. Each entry carries its resolved `panel_role`.
    """
    session_guilds = session.get("guilds", [])
    if not session_guilds:
        return []

    all_ids = [g["id"] for g in session_guilds]
    bot_guild_ids, configured_ids = await asyncio.gather(
        _fetch_bot_guild_ids(), _guild_ids_with_config(all_ids)
    )

    # Resolve panel roles only for bot-present guilds (role config can't exist
    # otherwise), so the fan-out stays bounded.
    probe_targets = [gid for gid in all_ids if gid in bot_guild_ids]
    role_results = await asyncio.gather(
        *(resolve_panel_role(session, gid) for gid in probe_targets),
        return_exceptions=True,
    )
    panel_roles = {
        gid: (r if isinstance(r, str) else "none")
        for gid, r in zip(probe_targets, role_results)
    }

    out: list[dict] = []
    for guild in session_guilds:
        gid = guild["id"]
        perms = int(guild.get("permissions", 0))
        has_manage = (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION
        panel_role = panel_roles.get(gid, "none")
        if not has_manage and panel_role == "none":
            continue
        bot_present = gid in bot_guild_ids
        out.append({
            "id": gid,
            "name": guild["name"],
            "icon": guild.get("icon"),
            "bot_in_guild": bot_present,
            "has_config": gid in configured_ids,
            "setup_required": not bot_present,
            "panel_role": panel_role if panel_role != "none" else ("admin" if has_manage else "none"),
        })

    return out


@router.get("/bot-invite-url")
async def bot_invite_url():
    """Return the Codex bot invite URL with required permissions."""
    if not BOT_TOKEN:
        return {"url": None}

    now = time.monotonic()
    if _bot_id_cache["id"] and now - _bot_id_cache["ts"] < _CACHE_TTL:
        bot_id = _bot_id_cache["id"]
    else:
        async with _bot_id_lock:
            now = time.monotonic()
            if _bot_id_cache["id"] and now - _bot_id_cache["ts"] < _CACHE_TTL:
                bot_id = _bot_id_cache["id"]
            else:
                async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
                    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
                    resp = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("Retry-After", "2"))
                        logger.info("Bot user rate-limited, retrying in %.1fs", retry_after)
                        await asyncio.sleep(retry_after)
                        resp = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
                    if resp.status_code != 200:
                        logger.warning("Failed to fetch bot user info: %s", resp.status_code)
                        return {"url": None}
                    bot_id = resp.json()["id"]
                    _bot_id_cache["id"] = bot_id
                    _bot_id_cache["ts"] = now

    # Least-privilege invite — the specific permissions TheCodex uses, NOT
    # Administrator (8). Covers posting messages/embeds, managing its own
    # discussion threads, managing the whitelist/tag/guide roles, and kicking
    # under-age accounts.
    permissions = (
        (1 << 10)    # View Channels
        | (1 << 11)  # Send Messages
        | (1 << 6)   # Add Reactions
        | (1 << 13)  # Manage Messages (thread cleanup, embed clone)
        | (1 << 14)  # Embed Links
        | (1 << 16)  # Read Message History
        | (1 << 34)  # Manage Threads
        | (1 << 35)  # Create Public Threads
        | (1 << 38)  # Send Messages in Threads
        | (1 << 28)  # Manage Roles (whitelist / tag / guide role toggles)
        | (1 << 1)   # Kick Members (auto-kick under-age accounts)
    )
    url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={bot_id}"
        f"&permissions={permissions}"
        f"&scope=bot%20applications.commands"
    )
    return {"url": url}


# ── Channel & Role endpoints ─────────────────────────────────────────────

_channels_cache: dict[str, dict] = {}  # guild_id -> {"data": [...], "ts": float}
_roles_cache: dict[str, dict] = {}
_RESOURCE_CACHE_TTL = 60  # 60 seconds


@router.get("/guilds/{guild_id}/channels")
async def guild_channels(
    guild_id: str,
    _session: dict = Depends(require_guild_manage),
):
    """Return text channels for a guild (filtered, cached 60s)."""
    now = time.monotonic()
    cached = _channels_cache.get(guild_id)
    if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
        return cached["data"]

    async with _channels_locks[guild_id]:
        now = time.monotonic()
        cached = _channels_cache.get(guild_id)
        if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
            return cached["data"]

        if not BOT_TOKEN:
            raise HTTPException(status_code=503, detail="Bot token not configured")

        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                await asyncio.sleep(retry_after)
                resp = await client.get(
                    f"{DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers
                )
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch channels for guild %s: %s",
                    guild_id,
                    resp.status_code,
                )
                return []

        channels = [
            {
                "id": ch["id"],
                "name": ch["name"],
                "type": ch["type"],
                "position": ch.get("position", 0),
            }
            for ch in resp.json()
            if ch["type"] == 0  # GUILD_TEXT
        ]
        channels.sort(key=lambda c: c["position"])

        _channels_cache[guild_id] = {"data": channels, "ts": now}
        return channels


@router.get("/guilds/{guild_id}/roles")
async def guild_roles(
    guild_id: str,
    _session: dict = Depends(require_guild_manage),
):
    """Return assignable roles for a guild (filtered, cached 60s)."""
    now = time.monotonic()
    cached = _roles_cache.get(guild_id)
    if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
        return cached["data"]

    async with _roles_locks[guild_id]:
        now = time.monotonic()
        cached = _roles_cache.get(guild_id)
        if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
            return cached["data"]

        if not BOT_TOKEN:
            raise HTTPException(status_code=503, detail="Bot token not configured")

        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/guilds/{guild_id}/roles", headers=headers
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                await asyncio.sleep(retry_after)
                resp = await client.get(
                    f"{DISCORD_API_BASE}/guilds/{guild_id}/roles", headers=headers
                )
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch roles for guild %s: %s",
                    guild_id,
                    resp.status_code,
                )
                return []

        roles = [
            {
                "id": r["id"],
                "name": r["name"],
                "color": r.get("color", 0),
                "position": r.get("position", 0),
            }
            for r in resp.json()
            if r.get("position", 0) > 0 and not r.get("managed", False)
        ]
        roles.sort(key=lambda r: r["position"])

        _roles_cache[guild_id] = {"data": roles, "ts": now}
        return roles
