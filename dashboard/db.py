"""MongoDB clients for the dashboard service.

Two clients: ``_client`` (MONGO_URI) holds Codex's own data (Guide, Settings, Daily,
Suggestions, ServerData); ``_shared_client`` (SHARED_SESSIONS_URI) holds the shared
cross-bot session store (WebSessions.SharedSessions + WebSessions.OAuthStates), kept on
its own client so the SSO store can live on a separate Mongo. SHARED_SESSIONS_URI is
required and has no fallback - see the note in ``config.py`` for why inheriting MONGO_URI
was the wrong default here.
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
    # Dedicated client for the shared cross-bot session store. Its URI is validated at
    # import time in config.py, so it is always explicitly set by the time we get here.
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


def user_privacy():
    """Settings.UserPrivacy - per-user data-collection opt-out, one document per user.

    Bot-side registry key `settings_user_privacy`. Keyed by `user_id` (string, unique
    index declared bot side); `features` holds the five opt-out booleans. A missing
    document means every toggle is off, so the absence of a document is a valid state
    and must never be treated as an error.
    """
    return _get_client()["Settings"]["UserPrivacy"]


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


def daily_wyr():
    """Daily.WYR - the question bank (shared `scope: global` + per-guild `scope: guild`)."""
    return _get_client()["Daily"]["WYR"]


def daily_wyr_votes():
    """Daily.WYR_Votes - one document per (question, guild, user). `created_at` on insert."""
    return _get_client()["Daily"]["WYR_Votes"]


def daily_wyr_mappings():
    """Daily.WYR_Mappings - what was posted where: message_id / question_id / channel_id."""
    return _get_client()["Daily"]["WYR_Mappings"]


def daily_wyr_submissions():
    """Daily.WYR_Submissions - member-submitted questions awaiting a moderator decision."""
    return _get_client()["Daily"]["WYR_Submissions"]


def daily_wyr_notify_prefs():
    """Daily.WYR_NotifyPrefs - per-member WYR notification preferences, one per (guild, user)."""
    return _get_client()["Daily"]["WYR_NotifyPrefs"]


def suggestions_suggestions():
    """Suggestions.Suggestions - user-submitted suggestions."""
    return _get_client()["Suggestions"]["Suggestions"]


def suggestions_votes():
    """Suggestions.Votes - one document per (suggestion, user).

    Carries NO guild_id - the guild is only on the suggestion document, so any
    guild-scoped vote figure has to join through `suggestion_id`.
    """
    return _get_client()["Suggestions"]["Votes"]


def suggestions_userstats():
    """Suggestions.UserStats - aggregated suggestion user stats."""
    return _get_client()["Suggestions"]["UserStats"]


def suggestions_notification_queue():
    """Suggestions.NotificationQueue - queued suggestion DMs.

    Carries NO guild_id, exactly like Suggestions.Votes - the guild only exists on
    the suggestion document, so guild scoping has to join through `suggestion_id`.
    """
    return _get_client()["Suggestions"]["NotificationQueue"]


def serverdata_boosts():
    """ServerData.Boosts - active boost records."""
    return _get_client()["ServerData"]["Boosts"]


def serverdata_feature_usage():
    """ServerData.FeatureUsage - per-guild, per-day feature usage counters.

    Written by Features/trackers/usage/usage_tracker.py. Aggregate only: no user
    id is stored, by design, so nothing here is personal data.
    """
    return _get_client()["ServerData"]["FeatureUsage"]


def serverdata_boost_events():
    """ServerData.Boost_Events - the boost start/stop event history per (guild, user)."""
    return _get_client()["ServerData"]["Boost_Events"]


def serverdata_guilds():
    """ServerData.Guilds - the guild snapshot root doc, keyed by `id` (string)."""
    return _get_client()["ServerData"]["Guilds"]


def serverdata_members():
    """ServerData.Members - per-member snapshot rows, keyed by (guild_id, id)."""
    return _get_client()["ServerData"]["Members"]


def serverdata_roles():
    """ServerData.Roles - per-role snapshot rows, keyed by (guild_id, id)."""
    return _get_client()["ServerData"]["Roles"]


def serverdata_whitelist():
    """ServerData.Whitelist - new-member whitelist entries (soft-deleted via is_active)."""
    return _get_client()["ServerData"]["Whitelist"]


def color_sets():
    """Settings.ColorSets - named embed colour palettes, per guild."""
    return _get_client()["Settings"]["ColorSets"]


def color_set_assignments():
    """Settings.ColorSetAssignments - which tier/role a colour set is granted to."""
    return _get_client()["Settings"]["ColorSetAssignments"]


def updates_monthly():
    """Updates-Drops.StatsMonthly - drop counts pre-bucketed into a compound _id."""
    return _get_client()["Updates-Drops"]["StatsMonthly"]


def updates_totals():
    """Updates-Drops.StatsTotals - all-time drop counts per (guild_id, coll)."""
    return _get_client()["Updates-Drops"]["StatsTotals"]