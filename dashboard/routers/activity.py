"""User activity API - aggregates WYR, Suggestions, Submissions, Tag Tracker, Boost data."""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.auth.dependencies import get_current_user
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE
from dashboard.routers.dashboard import _fetch_bot_guild_ids
from dashboard.services.overview import (
    TREND_DAYS,
    consecutive_day_streak,
    fill_trend,
    vote_totals,
)
from dashboard import db
from storage.log import get_logger

logger = get_logger("dashboard.routers.activity")

_TAG_TIMEOUT = httpx.Timeout(2.0, connect=2.0)

#: How far back the per-day vote history is read. Bounded because the only index
#: that can serve a user-scoped WYR_Votes read is the one on ``created_at`` -
#: the unique index puts user_id third, so it cannot answer a user-only match.
#: A streak longer than this is not worth the extra scan to prove.
_VOTE_HISTORY_DAYS = 400

#: The member's own suggestions returned with their outcome.
_SUGGESTION_ITEMS_LIMIT = 25

#: Submission statuses that are still waiting on a moderator
#: (``Features/daily/wyr_submissions.py`` OPEN_STATUSES).
_SUBMISSION_OPEN = ("pending", "reviewing")

router = APIRouter(tags=["activity"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _guild_scoped_match(user_id: int, guild_ids: list[int]) -> dict:
    """``{user_id, guild_id?}`` in the stored STRING form.

    An empty guild list means "no scoping", matching the behaviour the WYR
    leaderboard read has always had - an int id matches nothing, silently.
    """
    match: dict = {"user_id": str(user_id)}
    guild_id_strs = [str(gid) for gid in guild_ids]
    if guild_id_strs:
        match["guild_id"] = {"$in": guild_id_strs}
    return match


async def _get_vote_days(user_id: int, guild_ids: list[int]) -> dict[str, int]:
    """{YYYY-MM-DD: votes} for this member, over the bounded history window.

    Read from ``Daily.WYR_Votes`` (one document per question/guild/user, stamped
    ``created_at`` on insert), which is the only place a real per-day history
    exists - the leaderboard document holds running totals with no dates.
    """
    match = _guild_scoped_match(user_id, guild_ids)
    match["created_at"] = {
        "$gte": datetime.now(timezone.utc) - timedelta(days=_VOTE_HISTORY_DAYS)
    }
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d", "date": "$created_at", "timezone": "UTC",
            }},
            "count": {"$sum": 1},
        }},
    ]
    cursor = await db.daily_wyr_votes().aggregate(pipeline)
    return {doc["_id"]: doc["count"] async for doc in cursor if doc.get("_id")}


async def _get_vote_format_counts(user_id: int, guild_ids: list[int]) -> dict[str, int]:
    """Votes grouped by the question format stamped on the vote document.

    Open questions post no vote buttons, so no "open" vote is ever recorded -
    the UI must say "not counted" for them rather than zero. Votes written
    before the format stamp existed, or whose bank question was deleted before
    the backfill could classify them, group under "unclassified".
    """
    pipeline = [
        {"$match": _guild_scoped_match(user_id, guild_ids)},
        {"$group": {
            "_id": {"$ifNull": ["$format", "unclassified"]},
            "count": {"$sum": 1},
        }},
    ]
    cursor = await db.daily_wyr_votes().aggregate(pipeline)
    counts = {"wyr": 0, "poll": 0, "unclassified": 0}
    async for doc in cursor:
        key = doc.get("_id") or "unclassified"
        counts[key] = counts.get(key, 0) + doc["count"]
    return counts


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
            # Five options, because the poll format carries up to five. Anything
            # below five under-reports the breakdown against total_votes, which
            # is a separate stored field and is NOT derived from these sums.
            # $ifNull covers the leaderboard rows written before options 4 and 5
            # existed - those docs simply have no option4_votes/option5_votes key.
            "option1": {"$sum": {"$ifNull": ["$option1_votes", 0]}},
            "option2": {"$sum": {"$ifNull": ["$option2_votes", 0]}},
            "option3": {"$sum": {"$ifNull": ["$option3_votes", 0]}},
            "option4": {"$sum": {"$ifNull": ["$option4_votes", 0]}},
            "option5": {"$sum": {"$ifNull": ["$option5_votes", 0]}},
            "first_vote": {"$min": "$first_vote"},
            "last_vote": {"$max": "$last_vote"},
        }},
    ]
    cursor, vote_days, format_counts = await asyncio.gather(
        db.wyr_leaderboard().aggregate(pipeline),
        _get_vote_days(user_id, guild_ids),
        _get_vote_format_counts(user_id, guild_ids),
    )
    result = await cursor.to_list(1)

    # Real per-day history. `streak_days` is the consecutive-day run and is a
    # different measurement from `streak_active` below, which only asks whether
    # the member voted within the last day - both stay on the wire.
    trend = fill_trend(vote_days, TREND_DAYS)
    recent_days = {point["date"] for point in trend if point["votes"] > 0}
    history = {
        "streak_days": consecutive_day_streak(set(vote_days)),
        "trend": trend,
        "days_voted_30d": len(recent_days),
    }

    if not result:
        return {
            "total_votes": 0,
            "option_breakdown": {"option1": 0, "option2": 0, "option3": 0,
                                 "option4": 0, "option5": 0},
            "format_breakdown": format_counts,
            "first_vote": None,
            "last_vote": None,
            "streak_active": False,
            **history,
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
            "option4": doc["option4"],
            "option5": doc["option5"],
        },
        "format_breakdown": format_counts,
        "first_vote": first_vote.isoformat() if first_vote else None,
        "last_vote": last_vote.isoformat() if last_vote else None,
        "streak_active": streak_active,
        **history,
    }


async def _get_suggestions_activity(user_id: int, guild_ids: list[int]) -> dict:
    """Aggregate suggestion stats for the user across guilds (string-keyed IDs)."""
    match = {"user_id": str(user_id), "guild_id": {"$in": [str(g) for g in guild_ids]}}

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
    user_stats = await db.suggestions_userstats().find_one({"user_id": str(user_id)})
    if user_stats:
        votes_cast = user_stats.get("votes_cast", 0)

    # The member's own suggestions with the outcome they came to see. The vote
    # figure needs a join: Suggestions.Votes carries no guild_id, only
    # suggestion_id, so the count starts from these ids and joins back.
    item_docs = [
        doc async for doc in db.suggestions_suggestions().find(
            match,
            {"suggestion_id": 1, "text": 1, "status": 1, "created_at": 1},
            sort=[("created_at", -1)],
            limit=_SUGGESTION_ITEMS_LIMIT,
        )
    ]
    totals = await vote_totals([d["suggestion_id"] for d in item_docs if d.get("suggestion_id")])
    items = [
        {
            "suggestion_id": str(doc.get("suggestion_id") or ""),
            "text": doc.get("text") or "",
            "status": doc.get("status") or "Pending",
            "votes": totals.get(doc.get("suggestion_id"), 0),
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
        }
        for doc in item_docs
    ]

    return {
        "submitted": total,
        "votes_cast": votes_cast,
        "by_status": by_status,
        "last_activity": last_activity,
        "items": items,
    }


async def _get_submissions_activity(user_id: int, guild_ids: list[int]) -> dict:
    """The member's own question submissions and what became of them.

    Closes the loop the question bank exists to close: a member who sends in a
    question can see whether it was used, is still waiting, or was turned down.
    """
    match = _guild_scoped_match(user_id, guild_ids)

    status_cursor, format_cursor = await asyncio.gather(
        db.daily_wyr_submissions().aggregate([
            {"$match": match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]),
        # Submissions record their intended format on write, so this needs no
        # join and no backfill - unlike votes.
        db.daily_wyr_submissions().aggregate([
            {"$match": match},
            {"$group": {
                "_id": {"$ifNull": ["$format", "unclassified"]},
                "count": {"$sum": 1},
            }},
        ]),
    )
    counts: dict[str, int] = {}
    async for doc in status_cursor:
        if doc.get("_id"):
            counts[doc["_id"]] = counts.get(doc["_id"], 0) + doc["count"]

    by_format = {"wyr": 0, "poll": 0, "open": 0}
    async for doc in format_cursor:
        key = doc.get("_id") or "unclassified"
        by_format[key] = by_format.get(key, 0) + doc["count"]

    sent = sum(counts.values())
    posted = counts.get("approved", 0)
    waiting = sum(counts.get(status, 0) for status in _SUBMISSION_OPEN)
    declined = counts.get("rejected", 0)

    latest_posted = None
    if posted:
        approved_match = dict(match)
        approved_match["status"] = "approved"
        latest = await db.daily_wyr_submissions().find_one(
            approved_match,
            {"question_id": 1, "guild_id": 1},
            sort=[("reviewed_at", -1)],
        )
        if latest:
            latest_posted = await _resolve_posted_question(
                latest.get("question_id"), latest.get("guild_id")
            )

    return {
        "sent": sent,
        "posted": posted,
        "waiting": waiting,
        "declined": declined,
        "by_format": by_format,
        "latest_posted": latest_posted,
    }


async def _resolve_posted_question(question_number, guild_id) -> dict | None:
    """Look up when an approved submission's question went up, and its votes.

    ``question_id`` on a submission is the INT question number, not the
    ObjectId - the bank document's ``_id`` is what WYR_Votes stores, so this has
    to resolve one to the other before it can count anything.
    """
    if question_number is None:
        return None
    entry: dict = {"question_id": question_number, "posted_at": None, "votes": None}
    if guild_id is None:
        return entry

    gid = str(guild_id)
    question = await db.daily_wyr().find_one(
        {"id": question_number}, {"guilds": 1}
    )
    if not question:
        # Approved, but the bank document is gone - the number is still true.
        return entry

    guild_block = (question.get("guilds") or {}).get(gid) or {}
    last_posted = guild_block.get("last_posted")
    if isinstance(last_posted, datetime):
        entry["posted_at"] = last_posted.isoformat()
    entry["votes"] = await db.daily_wyr_votes().count_documents(
        {"question_id": question["_id"], "guild_id": gid}
    )
    return entry


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
        "user_id": str(user_id),
        "guild_id": {"$in": [str(g) for g in guild_ids]},
    })
    now = datetime.now(timezone.utc)
    boosts = []
    async for doc in cursor:
        gid = int(doc["guild_id"])
        boost_start = doc.get("boost_start")
        # Whole days boosting. Stored timestamps are UTC; a naive one is read as
        # UTC rather than dropped, which is what every other reader here does.
        duration_days = None
        if isinstance(boost_start, datetime):
            started = (
                boost_start.replace(tzinfo=timezone.utc)
                if boost_start.tzinfo is None else boost_start
            )
            duration_days = max((now - started).days, 0)
        boosts.append({
            "guild_id": str(gid),
            "guild_name": guild_name_map.get(gid, "Unknown"),
            "boost_start": boost_start.isoformat() if boost_start else None,
            "duration_days": duration_days,
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

    wyr, suggestions, tags, boost, submissions = await asyncio.gather(
        _get_wyr_activity(user_id_int, target_ids),
        _get_suggestions_activity(user_id_int, target_ids),
        _get_tag_status(user_id_str, target_ids, guild_name_map),
        _get_boost_status(user_id_int, target_ids, guild_name_map),
        _get_submissions_activity(user_id_int, target_ids),
    )

    return {
        "wyr": wyr,
        "suggestions": suggestions,
        "tag_tracker": tags,
        "boost": boost,
        "submissions": submissions,
    }
