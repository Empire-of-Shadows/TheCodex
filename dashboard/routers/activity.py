"""User activity API - aggregates WYR, Suggestions, Tag Tracker, Boost data."""

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.auth.dependencies import get_current_user
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE
from dashboard.routers.dashboard import _fetch_bot_guild_ids
from dashboard import db
from storage.log import get_logger

logger = get_logger("dashboard.routers.activity")

_TAG_TIMEOUT = httpx.Timeout(2.0, connect=2.0)

router = APIRouter(tags=["activity"])


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_wyr_activity(user_id: int, guild_ids: list[int]) -> dict:
    """Aggregate WYR voting stats for the user across the specified guilds."""
    guild_id_strs = [str(gid) for gid in guild_ids]
    match: dict = {"user_id": str(user_id)}
    if guild_id_strs:
        match["guild_id"] = {"$in": guild_id_strs}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_votes": {"$sum": {"$ifNull": ["$total_votes", 0]}},
            "option1": {"$sum": {"$ifNull": ["$option1_votes", 0]}},
            "option2": {"$sum": {"$ifNull": ["$option2_votes", 0]}},
            "option3": {"$sum": {"$ifNull": ["$option3_votes", 0]}},
            "first_vote": {"$min": "$first_vote"},
            "last_vote": {"$max": "$last_vote"},
        }},
    ]
    cursor = await db.wyr_leaderboard().aggregate(pipeline)
    result = await cursor.to_list(1)
    if not result:
        return {
            "total_votes": 0,
            "option_breakdown": {"option1": 0, "option2": 0, "option3": 0},
            "first_vote": None,
            "last_vote": None,
            "streak_active": False,
        }

    doc = result[0]
    last_vote = doc.get("last_vote")
    streak_active = False
    if last_vote:
        now = datetime.now(timezone.utc)
        diff = (now - last_vote.replace(tzinfo=timezone.utc)).days
        streak_active = diff <= 1

    first_vote = doc.get("first_vote")
    return {
        "total_votes": doc["total_votes"],
        "option_breakdown": {
            "option1": doc["option1"],
            "option2": doc["option2"],
            "option3": doc["option3"],
        },
        "first_vote": first_vote.isoformat() if first_vote else None,
        "last_vote": last_vote.isoformat() if last_vote else None,
        "streak_active": streak_active,
    }


async def _get_suggestions_activity(user_id: int, guild_ids: list[int]) -> dict:
    """Aggregate suggestion stats for the user across guilds."""
    match = {"user_id": user_id, "guild_id": {"$in": guild_ids}}

    # Count total + by status
    status_pipeline = [
        {"$match": match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_cursor = await db.suggestions_suggestions().aggregate(status_pipeline)
    by_status: dict[str, int] = {}
    total = 0
    last_activity = None

    async for doc in status_cursor:
        status = doc["_id"] or "Pending"
        by_status[status] = doc["count"]
        total += doc["count"]

    # Get last activity date
    last_doc = await db.suggestions_suggestions().find_one(
        match, sort=[("created_at", -1)], projection={"created_at": 1}
    )
    if last_doc and last_doc.get("created_at"):
        last_activity = last_doc["created_at"].isoformat()

    # Votes cast - check UserStats for quick lookup
    votes_cast = 0
    user_stats = await db.suggestions_userstats().find_one({"user_id": user_id})
    if user_stats:
        votes_cast = user_stats.get("votes_cast", 0)

    return {
        "submitted": total,
        "votes_cast": votes_cast,
        "by_status": by_status,
        "last_activity": last_activity,
    }


async def _check_tag_role(gid: int, user_id: str, role_id: str) -> bool | None:
    """Discord member lookup for tag-tracker role membership. Returns None on failure."""
    if not BOT_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TAG_TIMEOUT) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/guilds/{gid}/members/{user_id}",
                headers={"Authorization": f"Bot {BOT_TOKEN}"},
            )
        if resp.status_code == 200:
            member = resp.json()
            return str(role_id) in [str(r) for r in member.get("roles", [])]
    except httpx.HTTPError as e:
        logger.debug("Tag tracker API call failed for guild %s: %s", gid, e)
    return None


async def _get_tag_status(
    user_id: str, guild_ids: list[int], guild_name_map: dict[int, str]
) -> list[dict]:
    """Check tag tracker status for each guild (max 5). One config query, parallel role checks."""
    check_ids = guild_ids[:5]
    if not check_ids:
        return []

    cursor = db.guild_config().find(
        {"guild_id": {"$in": [str(g) for g in check_ids]}},
        {"guild_id": 1, "tag_tracker": 1},
    )
    configs: dict[int, dict] = {int(doc["guild_id"]): doc async for doc in cursor}

    # First pass: gather active tag configs and queue role-check tasks.
    entries: list[dict] = []
    role_tasks: list[asyncio.Future] = []
    for gid in check_ids:
        config_doc = configs.get(gid)
        if not config_doc:
            continue
        tt = config_doc.get("tag_tracker", {})
        if not tt.get("enabled"):
            continue
        server_tag = tt.get("server_tag")
        role_id = tt.get("role_id")
        if not server_tag:
            continue
        entries.append({
            "guild_id": str(gid),
            "guild_name": guild_name_map.get(gid, "Unknown"),
            "server_tag": server_tag,
            "has_role": None,
            "_role_id": role_id,
            "_gid": gid,
        })
        if role_id and BOT_TOKEN:
            role_tasks.append(asyncio.ensure_future(_check_tag_role(gid, user_id, role_id)))
        else:
            role_tasks.append(asyncio.ensure_future(asyncio.sleep(0, result=None)))

    role_results = await asyncio.gather(*role_tasks, return_exceptions=False)
    for entry, has_role in zip(entries, role_results):
        entry["has_role"] = has_role
        entry.pop("_role_id", None)
        entry.pop("_gid", None)

    return entries


async def _get_boost_status(user_id: int, guild_ids: list[int], guild_name_map: dict[int, str]) -> dict:
    """Check boost status for the user across guilds.

    The Boosts collection only holds active boosters - the tracker deletes the
    doc when a member stops boosting - so presence in the collection means active.
    """
    cursor = db.serverdata_boosts().find({
        "user_id": user_id,
        "guild_id": {"$in": guild_ids},
    })
    boosts = []
    async for doc in cursor:
        gid = doc["guild_id"]
        boost_start = doc.get("boost_start")
        boosts.append({
            "guild_id": str(gid),
            "guild_name": guild_name_map.get(gid, "Unknown"),
            "boost_start": boost_start.isoformat() if boost_start else None,
        })

    return {
        "is_boosting": len(boosts) > 0,
        "boosts": boosts,
    }


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.get("/user-activity")
async def user_activity(
    guild_id: str | None = Query(None),
    session: dict = Depends(get_current_user),
):
    """Return the logged-in user's activity across bot features."""
    user_data = session["user_data"]
    user_id_str = user_data["id"]
    user_id_int = int(user_id_str)

    # Build guild name map from session guilds
    session_guilds = {g["id"]: g["name"] for g in session.get("guilds", [])}

    if guild_id:
        # Scope to a single guild ONLY if the user is actually in it. Without
        # this check any authenticated user could pass an arbitrary guild_id and
        # drive bot-token Discord lookups (and read that guild's configured
        # server_tag / tag-tracker state) for servers they don't belong to.
        if guild_id not in session_guilds:
            raise HTTPException(
                status_code=404,
                detail="You are not a member of this guild (or session is stale).",
            )
        target_ids = [int(guild_id)]
        guild_name_map = {int(guild_id): session_guilds.get(guild_id, "Unknown")}
    else:
        bot_guild_ids = await _fetch_bot_guild_ids()
        # Intersection of user guilds and bot guilds
        common = set(session_guilds.keys()) & bot_guild_ids
        target_ids = [int(gid) for gid in common]
        guild_name_map = {int(gid): session_guilds[gid] for gid in common}

    wyr, suggestions, tags, boost = await asyncio.gather(
        _get_wyr_activity(user_id_int, target_ids),
        _get_suggestions_activity(user_id_int, target_ids),
        _get_tag_status(user_id_str, target_ids, guild_name_map),
        _get_boost_status(user_id_int, target_ids, guild_name_map),
    )

    return {
        "wyr": wyr,
        "suggestions": suggestions,
        "tag_tracker": tags,
        "boost": boost,
    }
