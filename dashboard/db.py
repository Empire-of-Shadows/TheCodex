"""Motor MongoDB client for the dashboard service.

Single client. Same Mongo holds Codex data (Guide, Settings, Daily, Suggestions,
ServerData) and the shared session store (WebSessions.SharedSessions +
WebSessions.OAuthStates).
"""

from pymongo import AsyncMongoClient

from dashboard.config import MONGO_URI

_client: AsyncMongoClient | None = None


async def connect():
    global _client
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI environment variable is required")
    _client = AsyncMongoClient(MONGO_URI)
    await _client.admin.command("ping")


async def close():
    global _client
    if _client:
        await _client.close()
        _client = None


def _get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("Database not connected - call connect() first")
    return _client


# Collection accessors matching define_collections.py mappings

def guide_content():
    """Guide.Content — one document per guild with full page tree."""
    return _get_client()["Guide"]["Content"]


def guild_config():
    """Settings.GuildConfig — per-guild configuration."""
    return _get_client()["Settings"]["GuildConfig"]


def audit_log():
    """Settings.AuditLog - admin setting mutation audit trail."""
    return _get_client()["Settings"]["AuditLog"]


def shared_sessions():
    """WebSessions.SharedSessions - cross-subdomain OAuth session storage."""
    return _get_client()["WebSessions"]["SharedSessions"]


def oauth_states():
    """WebSessions.OAuthStates - short-lived OAuth state for CSRF protection.

    TTL-indexed on `created_at` (10 minutes).
    """
    return _get_client()["WebSessions"]["OAuthStates"]


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