"""Motor MongoDB clients for the dashboard service.

Two independent clients:
- _client: Codex's primary data (Guide, Settings, Daily, Suggestions, ServerData).
- _shared_client: WebSessions.SharedSessions + WebSessions.OAuthStates - shared
  with TheHost and EcomBackend for SSO.

Codex's primary IS the canonical session Mongo (port 53002), so in practice
both clients connect to the same instance. They are kept distinct in code so
the SSO contract matches the other two services.
"""

from motor.motor_asyncio import AsyncIOMotorClient

from dashboard.config import MONGO_URI, SHARED_SESSIONS_URI

_client: AsyncIOMotorClient | None = None
_shared_client: AsyncIOMotorClient | None = None


async def connect():
    global _client, _shared_client
    if not MONGO_URI:
        raise RuntimeError("MONGO_PRIMARY_URI environment variable is required")
    if not SHARED_SESSIONS_URI:
        raise RuntimeError("SHARED_SESSIONS_URI environment variable is required")
    _client = AsyncIOMotorClient(MONGO_URI)
    _shared_client = AsyncIOMotorClient(SHARED_SESSIONS_URI)
    await _client.admin.command("ping")
    await _shared_client.admin.command("ping")


async def close():
    global _client, _shared_client
    if _client:
        _client.close()
        _client = None
    if _shared_client:
        _shared_client.close()
        _shared_client = None


def _get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("Database not connected - call connect() first")
    return _client


def _get_shared_client() -> AsyncIOMotorClient:
    if _shared_client is None:
        raise RuntimeError("Shared sessions database not connected - call connect() first")
    return _shared_client


# Collection accessors matching define_collections.py mappings

def guide_content():
    """Guide.Content — one document per guild with full page tree."""
    return _get_client()["Guide"]["Content"]


def guild_config():
    """Settings.GuildConfig — per-guild configuration."""
    return _get_client()["Settings"]["GuildConfig"]


def shared_sessions():
    """WebSessions.SharedSessions - cross-subdomain OAuth session storage.

    Reads from the dedicated shared-sessions Mongo client.
    """
    return _get_shared_client()["WebSessions"]["SharedSessions"]


def oauth_states():
    """WebSessions.OAuthStates - short-lived OAuth state for CSRF protection.

    TTL-indexed on `created_at` (10 minutes).
    """
    return _get_shared_client()["WebSessions"]["OAuthStates"]


def wyr_leaderboard():
    """Daily.WYR_Leaderboard — WYR voting stats per user."""
    return _get_client()["Daily"]["WYR_Leaderboard"]


def suggestions_suggestions():
    """Suggestions.Suggestions — user-submitted suggestions."""
    return _get_client()["Suggestions"]["Suggestions"]


def suggestions_userstats():
    """Suggestions.UserStats — aggregated suggestion user stats."""
    return _get_client()["Suggestions"]["UserStats"]


def serverdata_boosts():
    """ServerData.Boosts — active boost records."""
    return _get_client()["ServerData"]["Boosts"]
