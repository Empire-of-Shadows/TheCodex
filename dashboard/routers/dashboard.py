"""Dashboard API routes — user info and guild listing."""

import asyncio
import time
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, HTTPException

from dashboard.auth.dependencies import get_current_user, require_guild_manage
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE, MANAGE_GUILD_PERMISSION
from dashboard import db
from utils.logger import get_logger

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


@router.get("/me")
async def me(session: dict = Depends(get_current_user)):
    """Return the current user's info."""
    user = session["user_data"]
    return {
        "id": user["id"],
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
        "discriminator": user.get("discriminator"),
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
    """Return guilds where the user has MANAGE_GUILD permission, with bot status."""
    manageable = []
    for guild in session.get("guilds", []):
        perms = int(guild.get("permissions", 0))
        if (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION:
            manageable.append({
                "id": guild["id"],
                "name": guild["name"],
                "icon": guild.get("icon"),
            })

    if not manageable:
        return manageable

    guild_ids = [g["id"] for g in manageable]

    bot_guild_ids, configured_ids = await asyncio.gather(
        _fetch_bot_guild_ids(), _guild_ids_with_config(guild_ids)
    )

    for g in manageable:
        bot_present = g["id"] in bot_guild_ids
        has_config = g["id"] in configured_ids
        g["bot_in_guild"] = bot_present
        g["has_config"] = has_config
        g["setup_required"] = not bot_present and not has_config

    return manageable


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

    permissions = 8
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
