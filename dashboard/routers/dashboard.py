"""Dashboard API routes - user info and guild listing."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from dashboard._engine.discord_cache import discord_cache
from dashboard.auth.dependencies import get_current_user, require_guild_manage
from dashboard.auth.panel_role import resolve_panel_role
from dashboard.config import BOT_TOKEN, MANAGE_GUILD_PERMISSION
from dashboard import db
from storage.log import get_logger

logger = get_logger("dashboard.routers.dashboard")

router = APIRouter(tags=["dashboard"])


_ADMIN_PROBE_LIMIT = 25


@router.get("/me")
async def me(session: dict = Depends(get_current_user)):
    """Return the current user's info plus panel-access flags.

    Probe configured panel roles across bot-present session guilds:
    admin = MANAGE_GUILD anywhere OR a Panel Access role anywhere. There is no
    mod tier, so admin access is the only access.
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
        *(resolve_panel_role(session, gid, verify_manage_live=False) for gid in candidate_ids),
        return_exceptions=True,
    )
    roles = [r for r in results if isinstance(r, str)]
    can_access_admin_any = can_manage_any or any(r == "admin" for r in roles)

    return {
        "id": user["id"],
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
        "discriminator": user.get("discriminator"),
        "can_access_admin_any": can_access_admin_any,
        "can_access_settings_any": can_access_admin_any,
    }


async def _fetch_bot_guild_ids() -> set[str]:
    """The set of guild IDs the bot is currently in (engine TTL + single-flight cache)."""
    return await discord_cache.bot_guild_ids()


async def _guild_ids_with_config(guild_ids: list[str]) -> set[str]:
    """Return which of the given guild IDs have an existing guild config doc."""
    if not guild_ids:
        return set()

    cursor = db.guild_config().find(
        {"guild_id": {"$in": [str(gid) for gid in guild_ids]}},
        {"guild_id": 1},
    )
    return {str(doc["guild_id"]) async for doc in cursor}


@router.get("/guilds")
async def guilds(session: dict = Depends(get_current_user)):
    """Return guilds the user can manage, with bot status + role.

    Includes every session guild where the user holds MANAGE_GUILD (shown even
    when the bot is absent so they can invite it) or a configured Panel Access
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
        *(resolve_panel_role(session, gid, verify_manage_live=False) for gid in probe_targets),
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
    bot_id = await discord_cache.bot_id()
    if not bot_id:
        return {"url": None}

    # Least-privilege invite - the specific permissions TheCodex uses, NOT
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

@router.get("/guilds/{guild_id}/channels")
async def guild_channels(
    guild_id: str,
    _session: dict = Depends(require_guild_manage),
):
    """Return text channels for a guild (engine cache, 60s TTL)."""
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Bot token not configured")
    return await discord_cache.guild_text_channels(guild_id)


@router.get("/guilds/{guild_id}/roles")
async def guild_roles(
    guild_id: str,
    _session: dict = Depends(require_guild_manage),
):
    """Return assignable roles for a guild (engine cache, 60s TTL)."""
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Bot token not configured")
    return await discord_cache.guild_roles(guild_id)
