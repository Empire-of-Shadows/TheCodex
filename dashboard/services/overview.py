"""Guild overview aggregation for the admin home.

One round trip that answers "is this server's Codex actually doing anything, and
what did it do lately". Every section here is built independently so the router
can gather them with ``return_exceptions=True`` and null out whatever failed -
one slow or broken collection must never blank the whole page.

Read-only, by design. Nothing in this module writes, and nothing creates an
index; the queries below ride indexes that already exist
(``storage/settings/collections.py``).

Data sources, and the writers that fill them:

  - ``Daily.WYR``             question bank; per-guild usage under
                              ``guilds.<gid>.{used_count,last_posted,vote_counts}``
                              (``Features/daily/WYR.py`` increment_used_count / record_vote)
  - ``Daily.WYR_Votes``       one doc per (question, guild, user), ``created_at`` on insert
  - ``Daily.WYR_Mappings``    what was posted where (message/channel/question/created_at)
  - ``Daily.WYR_Submissions`` member submissions and their review outcome
  - ``Suggestions.*``         suggestions + votes (Votes has NO guild_id - join on
                              ``suggestion_id``, mirroring
                              ``SuggestionDatabaseManager.get_vote_totals``)
  - ``ServerData.*``          guild/member/role snapshots, whitelist, boosts
  - ``Updates-Drops.*``       drop counts, already bucketed by (guild, coll, year, month)

Two collections are deliberately NOT read: ``ServerData.Analytics`` and
``ServerData.Events`` have no writer in this bot, so anything sourced from them
would be a permanent zero dressed up as a measurement.

Every stored snowflake is a STRING (migrations m4-m10). Querying with an int
matches nothing, silently.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz

from dashboard import db
from storage.log import get_logger

logger = get_logger("dashboard.services.overview")

# How far back the trend / recent-activity windows look.
TREND_DAYS = 30
#: Months in the members and drops series.
MONTHS_BACK = 6
#: Newest pending suggestions surfaced on the overview.
PENDING_SUGGESTIONS_LIMIT = 5

# ── Mirrored bank rules ──────────────────────────────────────────────────────
#
# Copied, not imported: ``Features.daily.wyr_bank`` pulls in
# ``storage.settings.collections``, which builds the bot's own db_manager (a
# second Mongo client pool) at import time. The dashboard has its own client.
# Keep these in step with:
#   Features/daily/wyr_bank.py   FORMATS
#   Features/daily/WYR.py        DEFAULT_QUESTION_FORMATS,
#                                WYR._GLOBAL_SCOPE,
#                                WYR._build_scope_clause,
#                                WYR._build_formats_clause

#: Every format the bank accepts, in display order.
FORMATS: tuple[str, ...] = ("wyr", "poll", "open")
#: What a guild posts when its ``question_formats`` list is empty or unusable.
DEFAULT_QUESTION_FORMATS: tuple[str, ...] = ("wyr",)

#: Matches the shared bank. A question with no ``scope`` predates private banks,
#: and the bank was shared by every guild before then - so missing means global.
_GLOBAL_SCOPE: dict[str, Any] = {"$or": [{"scope": "global"}, {"scope": {"$exists": False}}]}

#: Drop tracker categories, in the order the panel declares them
#: (``admin/actions/drops_actions.py`` TRACKER_CATEGORIES). The order is part of
#: the contract: the chart colours a category by its index, so reordering here
#: moves colours between renders.
DROP_CATEGORIES: tuple[str, ...] = ("Updates", "Free", "Prime")

#: A member row this much older than the newest one in the guild was not in the
#: last snapshot, which means the member is gone. The snapshot writes all rows
#: in one bulk pass (chunked at 1000), so the spread within a single refresh is
#: seconds; an hour is a generous safety margin.
_MEMBER_STALE_AFTER = timedelta(hours=1)


# ── Small shared helpers ─────────────────────────────────────────────────────


def _iso(value: Any) -> str | None:
    """Datetime -> ISO-8601 string. Naive values are read as UTC (that is how
    every writer in this bot stores them). Anything else becomes None."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _guild_tz(timezone_name: Any) -> Any:
    """The guild's configured timezone, falling back to UTC on a bad value."""
    try:
        return pytz.timezone(str(timezone_name))
    except Exception:
        logger.debug("Unknown timezone %r on a guild config; using UTC", timezone_name)
        return pytz.UTC


def _localize(tz: Any, naive: datetime) -> datetime:
    """Attach ``tz`` to a naive local wall-clock time (pytz needs localize())."""
    localize = getattr(tz, "localize", None)
    if callable(localize):
        return localize(naive)
    return naive.replace(tzinfo=tz)


def _day_keys(days: int, *, end: Any = None) -> list[str]:
    """The last ``days`` YYYY-MM-DD keys in UTC, oldest first, ending today."""
    end_day = end or datetime.now(timezone.utc).date()
    start = end_day - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def fill_trend(counts: dict[str, int], days: int = TREND_DAYS) -> list[dict]:
    """Turn a sparse {YYYY-MM-DD: votes} map into a dense ``TrendPoint[]``.

    Zero-vote days are emitted, not skipped. A chart drawn from only the days
    that had votes reports a cadence the server never had.
    """
    return [{"date": key, "votes": int(counts.get(key, 0))} for key in _day_keys(days)]


def _month_keys(months: int) -> list[str]:
    """The last ``months`` YYYY-MM keys in UTC, oldest first, ending this month."""
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    keys: list[str] = []
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    return keys


def _window_start(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _daily_counts(collection, match: dict, date_field: str) -> dict[str, int]:
    """{YYYY-MM-DD: count} for one collection over an already-bounded match."""
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d", "date": f"${date_field}", "timezone": "UTC",
            }},
            "count": {"$sum": 1},
        }},
    ]
    cursor = await collection.aggregate(pipeline)
    return {doc["_id"]: doc["count"] async for doc in cursor if doc.get("_id")}


def consecutive_day_streak(day_keys: set[str]) -> int:
    """Length of the run of consecutive days ending today or yesterday.

    Yesterday counts as the anchor so a member who has not voted yet today does
    not watch their streak read zero until they do. Returns 0 when the most
    recent day is older than that.
    """
    if not day_keys:
        return 0
    today = datetime.now(timezone.utc).date()
    anchor = None
    for candidate in (today, today - timedelta(days=1)):
        if candidate.isoformat() in day_keys:
            anchor = candidate
            break
    if anchor is None:
        return 0
    streak = 0
    cursor = anchor
    while cursor.isoformat() in day_keys:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ── WYR question-bank filters (mirrored from the cog) ────────────────────────


def build_scope_clause(gid: str | None, question_source: str) -> dict | None:
    """Which bank this guild draws from. ``None`` means "nothing, ever".

    Mirrors ``WYR._build_scope_clause``. This clause is what keeps one server's
    private questions out of every other server; do not re-derive it differently.
    """
    if question_source == "global_only":
        return dict(_GLOBAL_SCOPE)
    if question_source == "guild_only":
        return {"scope": "guild", "guild_id": gid} if gid else None
    if gid is None:
        return dict(_GLOBAL_SCOPE)
    return {"$or": [{"scope": "global"},
                    {"scope": {"$exists": False}},
                    {"scope": "guild", "guild_id": gid}]}


def normalize_question_formats(question_formats: Any) -> list[str]:
    """The formats this guild actually posts, normalized the way the cog does."""
    wanted = [f for f in (question_formats or []) if f in FORMATS]
    return wanted or list(DEFAULT_QUESTION_FORMATS)


def build_formats_clause(wanted: list[str]) -> dict:
    """Restrict to the formats this guild posts. Mirrors ``WYR._build_formats_clause``.

    A question with no ``format`` predates the field and is a Would You Rather,
    so it is postable whenever "wyr" is wanted.
    """
    if len(wanted) == len(FORMATS):
        return {}
    if "wyr" in wanted:
        return {"$or": [{"format": {"$in": wanted}}, {"format": {"$exists": False}}]}
    return {"format": {"$in": wanted}}


# ── WYR ──────────────────────────────────────────────────────────────────────


async def _wyr_today(gid: str, wyr_cfg: dict) -> dict | None:
    """The question posted today in this guild, in the guild's own timezone.

    "Today" is the guild's local day because that is the day its schedule runs
    on - a UTC day boundary would call a 6pm Chicago post "yesterday" for six
    hours every morning.
    """
    tz = _guild_tz(wyr_cfg.get("timezone", "America/Chicago"))
    now_local = datetime.now(tz)
    day_start = _localize(tz, datetime(now_local.year, now_local.month, now_local.day))
    day_start_utc = day_start.astimezone(timezone.utc)

    mapping = await db.daily_wyr_mappings().find_one(
        {"guild_id": gid, "created_at": {"$gte": day_start_utc}},
        sort=[("created_at", -1)],
    )
    if not mapping:
        return None

    question_ref = mapping.get("question_id")
    question = None
    if question_ref is not None:
        question = await db.daily_wyr().find_one({"_id": question_ref})

    guild_block = ((question or {}).get("guilds") or {}).get(gid) or {}
    vote_counts = guild_block.get("vote_counts") or {}
    votes = sum(int(v) for v in vote_counts.values() if isinstance(v, (int, float)))

    # WYR_Votes is unique on (question_id, guild_id, user_id), so the document
    # count IS the distinct voter count - no $group needed.
    voters = 0
    if question_ref is not None:
        voters = await db.daily_wyr_votes().count_documents(
            {"question_id": question_ref, "guild_id": gid}
        )

    return {
        # The int question number people see, NOT the ObjectId.
        "question_id": (question or {}).get("id"),
        "text": (question or {}).get("original") or "",
        "format": (question or {}).get("format") or "wyr",
        "votes": votes,
        "voters": voters,
        "posted_at": _iso(mapping.get("created_at")),
        # The post itself. A thread opened from a message shares that message's
        # id, but thread creation can fail while the post succeeds (WYR.py
        # catches exactly that), so a "thread id" derived this way would be a
        # dead link on precisely the servers where something went wrong.
        # Linking to the message is correct either way - Discord shows the
        # thread from the message when one exists.
        "message_id": mapping.get("message_id"),
        "channel_id": mapping.get("channel_id"),
    }


async def _wyr_bank(gid: str, wyr_cfg: dict) -> dict:
    """Bank sizes as this guild sees them, plus what it can never post."""
    question_source = wyr_cfg.get("question_source", "both")
    wanted = normalize_question_formats(wyr_cfg.get("question_formats"))

    # "global" is what this guild MAY draw from, so it is gated on the source
    # setting: a guild_only server can see the shared bank exists but never
    # posts from it, and reporting its size as available would be wrong.
    draws_global = question_source in ("both", "global_only")

    collection = db.daily_wyr()

    global_count = 0
    if draws_global:
        global_count = await collection.count_documents(dict(_GLOBAL_SCOPE))

    # The guild's own private questions are a fact about the guild, so they are
    # counted whether or not question_source currently draws from them.
    guild_count = await collection.count_documents({"scope": "guild", "guild_id": gid})

    used_here = await collection.count_documents(
        {f"guilds.{gid}.used_count": {"$exists": True}}
    )

    # Unpostable: inside the visible bank, but in a format this guild switched
    # off. Zero unless the guild narrowed question_formats.
    unpostable = 0
    scope = build_scope_clause(gid, question_source)
    formats_clause = build_formats_clause(wanted)
    if scope is not None and formats_clause:
        unpostable = await collection.count_documents(
            {"$and": [scope, {"$nor": [formats_clause]}]}
        )

    return {
        "global": global_count,
        # The guild's own bank is a fact about the guild, reported whether or not
        # question_source currently draws from it.
        "guild": guild_count,
        "used_here": used_here,
        "formats": wanted,
        "unpostable": unpostable,
    }


async def build_wyr(gid: str, config_doc: dict) -> dict:
    """``WyrOverview`` - schedule, today's post, 30-day trend and bank health."""
    wyr_cfg = (config_doc or {}).get("wyr") or {}
    since = _window_start(TREND_DAYS)

    votes = db.daily_wyr_votes()
    trend_counts, voters_result, post_days, today, bank, pending = await asyncio.gather(
        _daily_counts(votes, {"guild_id": gid, "created_at": {"$gte": since}}, "created_at"),
        votes.distinct("user_id", {"guild_id": gid, "created_at": {"$gte": since}}),
        db.daily_wyr_mappings().distinct(
            "created_at", {"guild_id": gid, "created_at": {"$gte": since}}
        ),
        _wyr_today(gid, wyr_cfg),
        _wyr_bank(gid, wyr_cfg),
        db.daily_wyr_submissions().count_documents(
            {"guild_id": gid, "status": {"$in": ["pending", "reviewing"]}}
        ),
    )

    posted_days = {
        stamp.date().isoformat()
        for stamp in (_as_utc(s) for s in post_days)
        if stamp is not None
    }
    days_posted = len(posted_days)
    total_votes = sum(trend_counts.values())
    # Averaged over the days a question actually went up: dividing by a flat 30
    # would read as a drop in engagement on a server that simply posts less often.
    avg = round(total_votes / days_posted, 1) if days_posted else 0.0

    channel_id = wyr_cfg.get("channel_id")
    return {
        "enabled": bool(wyr_cfg.get("enabled", False)),
        "channel_id": str(channel_id) if channel_id is not None else None,
        "next_post_at": _next_post_at(wyr_cfg, today is not None),
        "today": today,
        "trend": fill_trend(trend_counts),
        "voters_30d": len(voters_result),
        "days_posted_30d": days_posted,
        "avg_votes_per_day": avg,
        "bank": bank,
        "submissions_pending": pending,
    }


def _next_post_at(wyr_cfg: dict, posted_today: bool) -> str | None:
    """When the daily question is next due, in the guild's own timezone.

    Null when the feature could not post anyway (off, or no channel). When today's
    slot has passed with nothing posted the value stays on today's slot: the tick
    loop does a catch-up post, so the next post really is imminent, not tomorrow.
    """
    if not wyr_cfg.get("enabled", False) or not wyr_cfg.get("channel_id"):
        return None
    tz = _guild_tz(wyr_cfg.get("timezone", "America/Chicago"))
    try:
        hour = int(wyr_cfg.get("post_hour", 6))
        minute = int(wyr_cfg.get("post_minute", 0))
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    now_local = datetime.now(tz)
    naive_slot = datetime(now_local.year, now_local.month, now_local.day, hour, minute)
    if posted_today:
        naive_slot += timedelta(days=1)
    return _localize(tz, naive_slot).isoformat()


# ── Suggestions ──────────────────────────────────────────────────────────────


async def vote_totals(suggestion_ids: list[str]) -> dict[str, int]:
    """{suggestion_id: vote count} for the given ids.

    Suggestions.Votes carries no guild_id, so a guild-scoped count has to start
    from guild-scoped suggestion ids and join back. Same shape the bot uses in
    ``SuggestionDatabaseManager.get_vote_totals``.
    """
    if not suggestion_ids:
        return {}
    pipeline = [
        {"$match": {"suggestion_id": {"$in": suggestion_ids}}},
        {"$group": {"_id": "$suggestion_id", "count": {"$sum": 1}}},
    ]
    cursor = await db.suggestions_votes().aggregate(pipeline)
    return {doc["_id"]: doc["count"] async for doc in cursor}


async def build_suggestions(gid: str, config_doc: dict) -> dict:
    """``SuggestionsOverview`` - the status split plus what is still waiting.

    Carries the configured suggestions channel because a Discord jump link needs
    a channel as well as a message, and the suggestion documents only store the
    message. Without it the "waiting on you" rows can only open the server,
    which defeats the point of listing them.
    """
    collection = db.suggestions_suggestions()
    channel_id = ((config_doc or {}).get("suggestions") or {}).get("channel_id")

    status_cursor = await collection.aggregate([
        {"$match": {"guild_id": gid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ])
    by_status: dict[str, int] = {}
    total = 0
    async for doc in status_cursor:
        status = doc["_id"] or "Pending"
        by_status[status] = by_status.get(status, 0) + doc["count"]
        total += doc["count"]

    pending_docs = [
        doc async for doc in collection.find(
            {"guild_id": gid, "status": "Pending"},
            {"suggestion_id": 1, "text": 1, "created_at": 1, "message_id": 1},
            sort=[("created_at", -1)],
            limit=PENDING_SUGGESTIONS_LIMIT,
        )
    ]
    totals = await vote_totals([d["suggestion_id"] for d in pending_docs if d.get("suggestion_id")])

    pending = [
        {
            "suggestion_id": str(doc.get("suggestion_id") or ""),
            "text": doc.get("text") or "",
            "votes": totals.get(doc.get("suggestion_id"), 0),
            "created_at": _iso(doc.get("created_at")),
            "message_id": doc.get("message_id"),
        }
        for doc in pending_docs
    ]

    return {
        "total": total,
        "by_status": by_status,
        "pending": pending,
        "channel_id": str(channel_id) if channel_id else None,
    }


# ── Members ──────────────────────────────────────────────────────────────────


async def build_members(gid: str) -> dict:
    """``MembersOverview`` - snapshot totals, joins, departures and whitelist size.

    ``total`` comes from the guild snapshot rather than counting member rows:
    the member snapshot only ever upserts, so rows for people who left are never
    removed and counting them would over-report the server.

    Departures are inferred: every member present at the last refresh has a
    fresh ``updated_at`` (the engine stamps it on every write), while someone
    who left keeps the timestamp from the last refresh that still saw them.
    """
    guild_doc, whitelisted = await asyncio.gather(
        db.serverdata_guilds().find_one(
            {"id": gid}, {"member_count": 1, "updated_at": 1}
        ),
        db.serverdata_whitelist().count_documents({"guild_id": gid, "is_active": True}),
    )

    members = db.serverdata_members()
    since_30d = _window_start(TREND_DAYS)
    month_keys = _month_keys(MONTHS_BACK)
    first_year, first_month = (int(part) for part in month_keys[0].split("-"))
    month_start = datetime(first_year, first_month, 1, tzinfo=timezone.utc)

    newest_cursor = await members.aggregate([
        {"$match": {"guild_id": gid}},
        {"$group": {"_id": None, "newest": {"$max": "$updated_at"}}},
    ])
    newest_rows = [doc async for doc in newest_cursor]
    newest_seen = _as_utc(newest_rows[0]["newest"]) if newest_rows else None

    left_30d = 0
    if newest_seen is not None:
        left_30d = await members.count_documents({
            "guild_id": gid,
            "updated_at": {"$lt": newest_seen - _MEMBER_STALE_AFTER, "$gte": since_30d},
        })

    joined_30d, monthly_counts = await asyncio.gather(
        members.count_documents({"guild_id": gid, "joined_at": {"$gte": since_30d}}),
        _joined_by_month(gid, month_start),
    )

    monthly = [
        {"month": key, "joined": int(monthly_counts.get(key, 0))}
        for key in month_keys
    ]

    # No snapshot yet is not the same fact as a server with nobody in it.
    total = (guild_doc or {}).get("member_count")
    return {
        "total": int(total) if isinstance(total, (int, float)) else None,
        "joined_30d": joined_30d,
        "left_30d": left_30d,
        "whitelisted": whitelisted,
        "monthly": monthly,
        "snapshot_at": _iso((guild_doc or {}).get("updated_at")),
    }


async def _joined_by_month(gid: str, since: datetime) -> dict[str, int]:
    cursor = await db.serverdata_members().aggregate([
        {"$match": {"guild_id": gid, "joined_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m", "date": "$joined_at", "timezone": "UTC",
            }},
            "count": {"$sum": 1},
        }},
    ])
    return {doc["_id"]: doc["count"] async for doc in cursor if doc.get("_id")}


# ── Drops ────────────────────────────────────────────────────────────────────


async def build_drops(gid: str, config_doc: dict) -> dict:
    """``DropsOverview`` - read straight off the pre-bucketed monthly counters.

    ``Updates-Drops.StatsMonthly`` is already keyed by
    ``_id: {coll, year, month, guild_id}`` with a matching index, so there is
    nothing to aggregate: the rows ARE the buckets.
    """
    drops_cfg = (config_doc or {}).get("drops") or {}
    wanted_months = _month_keys(MONTHS_BACK)
    buckets: dict[str, dict[str, int]] = {m: {c: 0 for c in DROP_CATEGORIES} for m in wanted_months}

    async for doc in db.updates_monthly().find({"_id.guild_id": gid}):
        key = doc.get("_id") or {}
        year, month, coll = key.get("year"), key.get("month"), key.get("coll")
        if not isinstance(year, int) or not isinstance(month, int):
            continue
        month_key = f"{year:04d}-{month:02d}"
        if month_key not in buckets or coll not in DROP_CATEGORIES:
            continue
        buckets[month_key][coll] += int(doc.get("count") or 0)

    this_month_key = wanted_months[-1]
    this_month = sum(buckets[this_month_key].values())

    all_time = 0
    async for doc in db.updates_totals().find({"_id.guild_id": gid}):
        if (doc.get("_id") or {}).get("coll") in DROP_CATEGORIES:
            all_time += int(doc.get("total_count") or 0)

    return {
        "enabled": bool(drops_cfg.get("enabled", False)),
        "this_month": this_month,
        "all_time": all_time,
        "categories": list(DROP_CATEGORIES),
        "monthly": [{"month": m, "counts": buckets[m]} for m in wanted_months],
    }


# ── Content ──────────────────────────────────────────────────────────────────


def _count_guide_pages(guide_data: Any) -> int:
    """Total pages in the tree, including nested children."""
    if not isinstance(guide_data, dict):
        return 0

    def walk(pages: Any) -> int:
        if not isinstance(pages, list):
            return 0
        return sum(
            1 + walk(page.get("children"))
            for page in pages
            if isinstance(page, dict)
        )

    return walk(guide_data.get("pages"))


async def build_content(gid: str, config_doc: dict) -> dict:
    """``ContentOverview`` - guide, board and greeting, with their edit stamps.

    ``updated_at`` / ``updated_by`` are real fields on the guide and board
    documents (``guide_store.save_guide`` / ``board_store.save_board``). The
    greeting lives inside GuildConfig and has no per-field stamp of its own -
    the config document's ``updated_at`` moves on ANY settings save, so
    reporting it as "greeting last edited" would be a fabrication.
    """
    guide_doc, board_doc = await asyncio.gather(
        db.guide_content().find_one(
            {"guild_id": gid}, {"guide_data": 1, "updated_at": 1, "updated_by": 1}
        ),
        db.board_content().find_one(
            {"guild_id": gid, "board_id": "main"},
            {"board_data": 1, "updated_at": 1, "updated_by": 1,
             "channel_id": 1, "message_id": 1, "posted_at": 1},
        ),
    )

    guide_data = (guide_doc or {}).get("guide_data")
    guide = {
        "exists": bool(guide_doc and guide_data),
        "count": _count_guide_pages(guide_data),
        "updated_at": _iso((guide_doc or {}).get("updated_at")),
        "updated_by": (guide_doc or {}).get("updated_by"),
    }

    board_data = (board_doc or {}).get("board_data")
    responses = (board_data or {}).get("responses") if isinstance(board_data, dict) else None
    board = {
        "exists": bool(board_doc and board_data),
        "count": len(responses) if isinstance(responses, list) else 0,
        "updated_at": _iso((board_doc or {}).get("updated_at")),
        "updated_by": (board_doc or {}).get("updated_by"),
        "posted_channel_id": (board_doc or {}).get("channel_id")
        if (board_doc or {}).get("message_id") else None,
        "posted_at": _iso((board_doc or {}).get("posted_at")),
    }

    components = ((config_doc or {}).get("new_members") or {}).get("greeting_components")
    has_greeting = bool(components)
    greeting = {
        "exists": has_greeting,
        "count": 1 if has_greeting else 0,
        "updated_at": None,
        "updated_by": None,
    }

    return {"guide": guide, "board": board, "greeting": greeting}


# ── Trackers ─────────────────────────────────────────────────────────────────


async def build_trackers(gid: str, config_doc: dict) -> dict:
    """``TrackersOverview`` - server-tag wearers and current boosters.

    ``wearing`` comes from the role snapshot's own ``member_count``
    (``storage/discord/extractors.py`` extract_roles). It is null when no role is
    configured or the snapshot has never seen it: "nobody is wearing the tag" and
    "we have never looked" must not render as the same zero.
    """
    tag_cfg = (config_doc or {}).get("tag_tracker") or {}
    role_id = tag_cfg.get("role_id")

    wearing = None
    if role_id is not None:
        role_doc = await db.serverdata_roles().find_one(
            {"guild_id": gid, "id": str(role_id)}, {"member_count": 1}
        )
        count = (role_doc or {}).get("member_count")
        if isinstance(count, (int, float)):
            wearing = int(count)

    boost_count, guild_doc = await asyncio.gather(
        db.serverdata_boosts().count_documents({"guild_id": gid}),
        db.serverdata_guilds().find_one({"id": gid}, {"premium_tier": 1}),
    )
    tier = (guild_doc or {}).get("premium_tier")

    server_tag = tag_cfg.get("server_tag")
    return {
        "tag": {
            "enabled": bool(tag_cfg.get("enabled", False)),
            "server_tag": str(server_tag) if server_tag else None,
            "wearing": wearing,
        },
        "boost": {
            "count": boost_count,
            "tier": int(tier) if isinstance(tier, (int, float)) else None,
        },
    }


# ── Feature usage ────────────────────────────────────────────────────────────

#: Recent window: "is this feature being used now".
USAGE_RECENT_DAYS = 30
#: Baseline window: "was it ever used". Must be comfortably longer than the recent
#: window or nothing can ever look like it went quiet.
USAGE_BASELINE_DAYS = 90
#: How many entries each list on the tile carries.
USAGE_LIST_LIMIT = 5


#: How far back the activity tile looks. The collection's TTL index drops rows at
#: 30 days, so asking for more than that can only ever return the same thing.
EVENTS_WINDOW_DAYS = 30
#: Most recent entries shown in the tile's list.
EVENTS_RECENT_LIMIT = 8


async def build_activity(gid: str) -> dict | None:
    """``ActivityOverview`` - what has changed in this server lately.

    Reads ServerData.Events, written by the listeners in
    ``Features/NewMembers/joining.py`` since 2026-08-17.

    Returns None when the guild has no events at all, so the tile renders an
    honest empty state rather than a row of zeros claiming nothing happened. That
    is the expected state everywhere at first, because the trail only started
    being written on 2026-08-17 and nothing backfills it.

    The counts are deliberately NOT a member census. `member_join` minus
    `member_remove` over 30 days is churn, not growth, and the tile labels it
    that way - the member section above it owns the actual totals, which come
    from the snapshot and are always current.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=EVENTS_WINDOW_DAYS)

    # Rides the (guild_id, created_at desc) index the collection declares. The
    # window bound is belt-and-braces next to the TTL: a row cannot outlive it,
    # but an index scan bounded by both is what the index was built for.
    rows = await db.serverdata_events().find(
        {"guild_id": gid, "created_at": {"$gte": cutoff}},
        {"event_type": 1, "data": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(length=1000)

    if not rows:
        return None

    breakdown: dict[str, int] = {}
    for row in rows:
        key = row.get("event_type") or "unknown"
        breakdown[key] = breakdown.get(key, 0) + 1

    def _describe(row: dict) -> dict:
        """One list row. Deliberately carries no user id to the browser.

        The stored join/departure rows are user-keyed, but nobody reading this
        tile needs to know WHO - the question it answers is "what has been
        happening here". Sending ids would put personal data on a screen that
        does not use it, so the shape stops at the event and its timestamp.
        """
        data = row.get("data") or {}
        event = row.get("event_type") or "unknown"
        name = data.get("name")
        previous = data.get("previous_name")
        return {
            "event_type": event,
            "name": name,
            "previous_name": previous,
            "at": row.get("created_at"),
        }

    return {
        "window_days": EVENTS_WINDOW_DAYS,
        "total_events": len(rows),
        "breakdown": breakdown,
        "joins": breakdown.get("member_join", 0),
        "departures": breakdown.get("member_remove", 0),
        "structural_changes": sum(
            n for k, n in breakdown.items()
            if k.startswith("role_") or k.startswith("channel_")
        ),
        "recent": [_describe(r) for r in rows[:EVENTS_RECENT_LIMIT]],
    }


async def build_feature_usage(gid: str) -> dict | None:
    """``FeatureUsageOverview`` - which parts of Codex are actually being used.

    Written by ``Features/trackers/usage/usage_tracker.py``. Aggregate only: the
    documents contain no user id at all, so nothing here is personal data.

    WHY "QUIET" MEANS *USED BEFORE, NOT NOW*
    ----------------------------------------
    The owner's reason for wanting this was "I don't remember why I stopped using
    those features", so the useful list is the ones that went quiet - not a
    popularity ranking, which buries exactly those.

    Saying "never used" would need the full command registry, and this process has
    no bot and no command tree to ask. Comparing two windows of the bot's own
    history needs neither: a feature with uses in the last 90 days but none in the
    last 30 has demonstrably been dropped, which is the actual question. It also
    self-maintains - a feature added or renamed later needs no list updating.

    Returns None when nothing has ever been recorded for this guild, so the tile
    can say "nothing recorded yet" instead of rendering a wall of honest zeros.
    Tracking only began 2026-08-17, so that is the expected state at first.
    """
    now = datetime.now(tz=timezone.utc)
    baseline_start = (now - timedelta(days=USAGE_BASELINE_DAYS)).strftime("%Y-%m-%d")
    recent_start = (now - timedelta(days=USAGE_RECENT_DAYS)).strftime("%Y-%m-%d")

    # At most USAGE_BASELINE_DAYS small documents - cheap to sum in Python, and it
    # rides the (guild_id, date) index the collection already declares.
    cursor = await db.serverdata_feature_usage().find(
        {"guild_id": gid, "date": {"$gte": baseline_start}},
        {"date": 1, "total": 1, "features": 1},
    ).to_list(length=USAGE_BASELINE_DAYS + 1)

    if not cursor:
        return None

    baseline: dict[str, int] = {}
    recent: dict[str, int] = {}
    last_seen: dict[str, str] = {}
    recent_total = 0

    for doc in cursor:
        date = doc.get("date") or ""
        is_recent = date >= recent_start
        if is_recent:
            recent_total += int(doc.get("total") or 0)
        for feature, payload in (doc.get("features") or {}).items():
            uses = int((payload or {}).get("total") or 0)
            if uses <= 0:
                continue
            baseline[feature] = baseline.get(feature, 0) + uses
            if date > last_seen.get(feature, ""):
                last_seen[feature] = date
            if is_recent:
                recent[feature] = recent.get(feature, 0) + uses

    # Used at some point in the baseline, not once in the recent window.
    quiet = [
        {"feature": f, "uses_before": n, "last_used": last_seen.get(f)}
        for f, n in baseline.items()
        if recent.get(f, 0) == 0
    ]
    quiet.sort(key=lambda row: (-row["uses_before"], row["feature"]))

    used_now = sorted(recent.items(), key=lambda kv: (kv[1], kv[0]))

    return {
        "recent_days": USAGE_RECENT_DAYS,
        "baseline_days": USAGE_BASELINE_DAYS,
        "total_uses": recent_total,
        "active_features": len(recent),
        "known_features": len(baseline),
        "quiet": quiet[:USAGE_LIST_LIMIT],
        "least_used": [
            {"feature": f, "uses": n} for f, n in used_now[:USAGE_LIST_LIMIT]
        ],
        "top": [
            {"feature": f, "uses": n} for f, n in reversed(used_now[-USAGE_LIST_LIMIT:])
        ],
    }


# ── Feature status rail ──────────────────────────────────────────────────────


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def build_features(
    config_doc: dict,
    *,
    wyr: dict | None,
    suggestions: dict | None,
    members: dict | None,
    drops: dict | None,
    content: dict | None,
    trackers: dict | None,
) -> list[dict]:
    """One ``FeatureStatus`` per feature, in the order the home page shows them.

    "needs_setup" is the state that earns this rail: enabled, looks alive, and
    missing the one value it cannot run without. A bot that reports itself online
    while silently doing nothing is the complaint this exists to answer.
    """
    config_doc = config_doc or {}
    wyr_cfg = config_doc.get("wyr") or {}
    new_members_cfg = config_doc.get("new_members") or {}
    suggestions_cfg = config_doc.get("suggestions") or {}
    guide_cfg = config_doc.get("guide") or {}
    drops_cfg = config_doc.get("drops") or {}
    tag_cfg = config_doc.get("tag_tracker") or {}
    boost_cfg = config_doc.get("boost") or {}
    announcement_cfg = config_doc.get("announcement") or {}

    features: list[dict] = []

    # -- Daily question ------------------------------------------------------
    if not wyr_cfg.get("enabled", False):
        state, detail = "off", "Turned off"
    elif not wyr_cfg.get("channel_id"):
        state, detail = "needs_setup", "No channel set"
    else:
        state = "on"
        today = (wyr or {}).get("today")
        if today:
            detail = f"Posted today - {_plural(int(today.get('votes') or 0), 'vote')}"
        elif wyr is not None and (wyr.get("bank") or {}).get("global", 0) == 0 \
                and (wyr.get("bank") or {}).get("guild", 0) == 0:
            state, detail = "needs_setup", "No questions in the bank yet"
        else:
            detail = "Nothing posted yet today"
    features.append({"key": "wyr", "label": "Daily Question", "state": state,
                     "detail": detail, "settings_key": "wyr"})

    # -- Suggestions ---------------------------------------------------------
    # No on/off switch: the channel is what makes it work at all.
    if not suggestions_cfg.get("channel_id"):
        state, detail = "needs_setup", "No channel set"
    else:
        state = "on"
        waiting = (suggestions or {}).get("by_status", {}).get("Pending", 0)
        detail = f"{waiting} waiting" if waiting else "Nothing waiting"
    features.append({"key": "suggestions", "label": "Suggestions", "state": state,
                     "detail": detail, "settings_key": "suggestions"})

    # -- New members ---------------------------------------------------------
    if not new_members_cfg.get("enabled", False):
        state, detail = "off", "Turned off"
    elif new_members_cfg.get("greeting_enabled", True) and not new_members_cfg.get("greeting_channel_id"):
        state, detail = "needs_setup", "No welcome channel set"
    else:
        state = "on"
        joined = (members or {}).get("joined_30d")
        detail = (
            f"{_plural(int(joined), 'new member')} in 30 days"
            if isinstance(joined, int) else "Watching new joins"
        )
    features.append({"key": "new_members", "label": "New Members", "state": state,
                     "detail": detail, "settings_key": "new_members"})

    # -- Guide ---------------------------------------------------------------
    guide_doc = (content or {}).get("guide") or {}
    if not guide_cfg.get("enabled", True):
        state, detail = "off", "Turned off"
    elif not guide_doc.get("exists"):
        state, detail = "needs_setup", "No pages written yet"
    else:
        state = "on"
        detail = _plural(int(guide_doc.get("count") or 0), "page")
    features.append({"key": "guide", "label": "Server Guide", "state": state,
                     "detail": detail, "settings_key": "guide"})

    # -- Info board ----------------------------------------------------------
    # Content-only: it has no settings section, so there is nothing to link to.
    board_doc = (content or {}).get("board") or {}
    if not board_doc.get("exists"):
        state, detail = "off", "Not built yet"
    elif not board_doc.get("posted_channel_id"):
        state, detail = "needs_setup", "Built but not posted"
    else:
        state = "on"
        detail = f"Posted - {_plural(int(board_doc.get('count') or 0), 'response')}"
    features.append({"key": "board", "label": "Info Board", "state": state,
                     "detail": detail, "settings_key": None})

    # -- Drops ---------------------------------------------------------------
    tracker_channels = drops_cfg.get("tracker_channels") or {}
    tracked = [name for name, value in tracker_channels.items() if value]
    if not drops_cfg.get("enabled", False):
        state, detail = "off", "Turned off"
    elif not tracked:
        state, detail = "needs_setup", "No channels being watched"
    else:
        state = "on"
        this_month = (drops or {}).get("this_month")
        detail = (
            f"{_plural(int(this_month), 'drop')} this month"
            if isinstance(this_month, int) else f"Watching {_plural(len(tracked), 'channel')}"
        )
    features.append({"key": "drops", "label": "Drops", "state": state,
                     "detail": detail, "settings_key": "drops"})

    # -- Trackers (server tag + boosts) --------------------------------------
    tag_on = bool(tag_cfg.get("enabled", False))
    boost_on = bool(boost_cfg.get("enabled", False))
    if not tag_on and not boost_on:
        state, detail = "off", "Turned off"
    elif tag_on and not (tag_cfg.get("server_tag") and tag_cfg.get("role_id")):
        state, detail = "needs_setup", "Server tag needs a tag and a role"
    elif boost_on and not boost_cfg.get("channel_id"):
        state, detail = "needs_setup", "Boost announcements need a channel"
    else:
        state = "on"
        parts = []
        wearing = ((trackers or {}).get("tag") or {}).get("wearing")
        if tag_on and isinstance(wearing, int):
            parts.append(f"{_plural(wearing, 'member')} wearing the tag")
        boosters = ((trackers or {}).get("boost") or {}).get("count")
        if boost_on and isinstance(boosters, int):
            parts.append(_plural(boosters, "booster"))
        detail = ", ".join(parts) if parts else "Watching"
    features.append({"key": "trackers", "label": "Trackers", "state": state,
                     "detail": detail, "settings_key": "trackers"})

    # -- Announcement threads ------------------------------------------------
    if not announcement_cfg.get("thread_auto_create", True):
        state, detail = "off", "Turned off"
    elif not announcement_cfg.get("channel_id"):
        state, detail = "needs_setup", "No channel set"
    else:
        state, detail = "on", "Opening a thread on each announcement"
    features.append({"key": "announcement", "label": "Announcement Threads", "state": state,
                     "detail": detail, "settings_key": "announcement"})

    return features
