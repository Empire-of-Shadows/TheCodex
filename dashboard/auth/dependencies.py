"""FastAPI dependencies for authentication."""

from fastapi import Cookie, Depends, HTTPException

from dashboard._engine.auth.panel_access import has_manage_guild
from dashboard._engine.auth.session import get_session, refresh_guilds_if_stale
from dashboard._engine.auth.signing import unsign_token
from dashboard.config import SESSION_COOKIE_NAME, MANAGE_GUILD_PERMISSION


async def get_current_user(
    codex_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """Dependency that returns the current authenticated user or raises 401."""
    if not codex_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    raw_token = unsign_token(codex_session)
    if raw_token is None:
        # Tampered or expired signature - reject without hitting Mongo.
        raise HTTPException(status_code=401, detail="Invalid session signature")
    session = await get_session(raw_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired")
    # Keep the cached guild list self-healing (best-effort; never raises).
    session = await refresh_guilds_if_stale(session)
    return session


def user_can_manage_guild(session: dict, guild_id: str) -> bool:
    """MANAGE_GUILD from the OAuth login snapshot (display hint only; authz uses the live check)."""
    for guild in session.get("guilds", []):
        if str(guild["id"]) == str(guild_id):
            perms = int(guild.get("permissions", 0))
            return (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION
    return False


async def require_guild_access(session: dict, guild_id: str):
    """Require LIVE MANAGE_GUILD for this guild (verified against Discord via the bot token)."""
    if not await has_manage_guild(session, guild_id):
        raise HTTPException(status_code=403, detail="No MANAGE_GUILD permission for this guild")


async def require_guild_manage(
    guild_id: str,
    session: dict = Depends(get_current_user),
) -> dict:
    """FastAPI dependency: 401 if anon, 403 if user lacks live MANAGE_GUILD. Returns the session."""
    await require_guild_access(session, guild_id)
    return session
