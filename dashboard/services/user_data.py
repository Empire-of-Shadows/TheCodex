"""User-scoped data export/delete for the Privacy page.

Codex user data lives in (all snowflake IDs stored as strings since the IS-4
normalization migrations):
  - Daily.WYR_Leaderboard      (user_id str, guild_id str)
  - Suggestions.Suggestions    (user_id str, guild_id str)
  - Suggestions.UserStats      (user_id str; not guild-scoped)
  - ServerData.Boosts          (user_id str, guild_id str)

Tag-tracker status is live Discord role membership, not user-owned data, so it
is neither exported nor deleted here.
"""

from __future__ import annotations

from dashboard import db


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


async def distinct_guild_ids(user_id: int) -> set[str]:
    """Guild ids (as strings) where the user has any Codex data."""
    ids: set[str] = set()
    async for d in db.wyr_leaderboard().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.suggestions_suggestions().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.serverdata_boosts().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    return ids


async def export_all(user_id: int, guild_id: int | None = None) -> dict:
    """Full dump of the user's Codex data, optionally scoped to one guild."""
    wyr_match: dict = {"user_id": str(user_id)}
    sugg_match: dict = {"user_id": str(user_id)}
    boost_match: dict = {"user_id": str(user_id)}
    if guild_id is not None:
        wyr_match["guild_id"] = str(guild_id)
        sugg_match["guild_id"] = str(guild_id)
        boost_match["guild_id"] = str(guild_id)

    wyr = [_strip(d) async for d in db.wyr_leaderboard().find(wyr_match)]
    suggestions = [_strip(d) async for d in db.suggestions_suggestions().find(sugg_match)]
    boosts = [_strip(d) async for d in db.serverdata_boosts().find(boost_match)]

    # UserStats is account-wide (not guild-scoped); only include for full export.
    suggestion_stats = None
    if guild_id is None:
        doc = await db.suggestions_userstats().find_one({"user_id": str(user_id)})
        suggestion_stats = _strip(doc) if doc else None

    return {
        "user_id": str(user_id),
        "guild_id": str(guild_id) if guild_id is not None else None,
        "wyr_votes": wyr,
        "suggestions": suggestions,
        "boosts": boosts,
        "suggestion_stats": suggestion_stats,
    }


async def delete_all(user_id: int, guild_id: int | None = None) -> dict[str, int]:
    """Delete the user's Codex data. Optionally scoped to one guild.

    Account-wide UserStats is only removed on a full (unscoped) delete.
    """
    wyr_match: dict = {"user_id": str(user_id)}
    sugg_match: dict = {"user_id": str(user_id)}
    boost_match: dict = {"user_id": str(user_id)}
    if guild_id is not None:
        wyr_match["guild_id"] = str(guild_id)
        sugg_match["guild_id"] = str(guild_id)
        boost_match["guild_id"] = str(guild_id)

    deleted: dict[str, int] = {}
    deleted["wyr_votes"] = (await db.wyr_leaderboard().delete_many(wyr_match)).deleted_count
    deleted["suggestions"] = (await db.suggestions_suggestions().delete_many(sugg_match)).deleted_count
    deleted["boosts"] = (await db.serverdata_boosts().delete_many(boost_match)).deleted_count
    if guild_id is None:
        deleted["suggestion_stats"] = (
            await db.suggestions_userstats().delete_many({"user_id": str(user_id)})
        ).deleted_count
    return deleted
