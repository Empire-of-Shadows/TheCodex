"""FastAPI dependencies for authentication."""

from fastapi import Cookie, HTTPException

from dashboard.auth.session import get_session
from dashboard.auth.signing import unsign_token
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
    return session


def user_can_manage_guild(session: dict, guild_id: str) -> bool:
    """Check if the user has MANAGE_GUILD permission for the given guild."""
    for guild in session.get("guilds", []):
        if guild["id"] == guild_id:
            perms = int(guild.get("permissions", 0))
            return (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION
    return False


def require_guild_access(session: dict, guild_id: str):
    """Raise 403 if user cannot manage the guild."""
    if not user_can_manage_guild(session, guild_id):
        raise HTTPException(status_code=403, detail="No MANAGE_GUILD permission for this guild")
