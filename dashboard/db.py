"""MongoDB clients for the dashboard service.

Two clients: ``_client`` (MONGO_URI) holds Codex's own data (Guide, Settings, Daily,
Suggestions, ServerData); ``_shared_client`` (SHARED_SESSIONS_URI) holds the shared
cross-bot session store (WebSessions.SharedSessions + WebSessions.OAuthStates), kept on
its own client so the SSO store can live on a separate Mongo. SHARED_SESSIONS_URI defaults
to MONGO_URI, so an un-split deployment behaves exactly as before.
"""

from pymongo import AsyncMongoClient

from dashboard.config import MONGO_URI, SHARED_SESSIONS_URI

_client: AsyncMongoClient | None = None
_shared_client: AsyncMongoClient | None = None


async def connect():
    global _client, _shared_client
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI environment variable is required")
    _client = AsyncMongoClient(MONGO_URI)
    await _client.admin.command("ping")
    # Dedicated client for the shared cross-bot session store (defaults to the same
    # Mongo as MONGO_URI unless SHARED_SESSIONS_URI splits it out).
    _shared_client = AsyncMongoClient(SHARED_SESSIONS_URI)
    await _shared_client.admin.command("ping")


async def close():
    global _client, _shared_client
    if _client:
        await _client.close()
        _client = None
    if _shared_client:
        await _shared_client.close()
        _shared_client = None


def _get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("Database not connected - call connect() first")
    return _client


def _get_shared_client() -> AsyncMongoClient:
    if _shared_client is None:
        raise RuntimeError("Database not connected - call connect() first")
    return _shared_client


# Collection accessors matching define_collections.py mappings

def guide_content():
    """Guide.Content - one document per guild with full page tree."""
    return _get_client()["Guide"]["Content"]


def board_content():
    """Board.Content - one document per guild per board (board_id is "main" today)."""
    return _get_client()["Board"]["Content"]


def guild_config():
    """Settings.GuildConfig - per-guild configuration."""
    return _get_client()["Settings"]["GuildConfig"]


def audit_log():
    """Settings.AuditLog - admin setting mutation audit trail."""
    return _get_client()["Settings"]["AuditLog"]


def shared_sessions():
    """WebSessions.SharedSessions - cross-subdomain OAuth session storage (shared client)."""
    return _get_shared_client()["WebSessions"]["SharedSessions"]


def oauth_states():
    """WebSessions.OAuthStates - short-lived OAuth state for CSRF protection (shared client).

    TTL-indexed on `created_at` (10 minutes).
    """
    return _get_shared_client()["WebSessions"]["OAuthStates"]


def wyr_leaderboard():
    """Daily.WYR_Leaderboard - WYR voting stats per user."""
    return _get_client()["Daily"]["WYR_Leaderboard"]


def suggestions_suggestions():
    """Suggestions.Suggestions - user-submitted suggestions."""
    return _get_client()["Suggestions"]["Suggestions"]


def suggestions_userstats():
    """Suggestions.UserStats - aggregated suggestion user stats."""
    return _get_client()["Suggestions"]["UserStats"]


def serverdata_boosts():
    """ServerData.Boosts - active boost records."""
    return _get_client()["ServerData"]["Boosts"]