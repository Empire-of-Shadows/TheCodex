"""Motor MongoDB client for the dashboard service."""

from motor.motor_asyncio import AsyncIOMotorClient

from dashboard.config import MONGO_URI

_client: AsyncIOMotorClient | None = None


async def connect():
    global _client
    _client = AsyncIOMotorClient(MONGO_URI)
    # Verify connectivity
    await _client.admin.command("ping")


async def close():
    global _client
    if _client:
        _client.close()
        _client = None


def _get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("Database not connected — call connect() first")
    return _client


# Collection accessors matching define_collections.py mappings

def guide_content():
    """Guide.Content — one document per guild with full page tree."""
    return _get_client()["Guide"]["Content"]


def guild_config():
    """Settings.GuildConfig — per-guild configuration."""
    return _get_client()["Settings"]["GuildConfig"]


def shared_sessions():
    """WebSessions.SharedSessions — cross-subdomain OAuth session storage."""
    return _get_client()["WebSessions"]["SharedSessions"]


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
