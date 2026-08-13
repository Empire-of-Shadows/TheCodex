"""User-scoped data export/delete for the Privacy page, plus the opt-out preferences.

Codex user data lives in (all snowflake IDs stored as strings since the IS-4
normalization migrations):

Guild-scoped, keyed by ``user_id``:
  - Daily.WYR_Leaderboard        (user_id, guild_id)
  - Daily.WYR_Votes              (user_id, guild_id, question_id)
  - Daily.WYR_Submissions        (user_id, guild_id)
  - Daily.WYR_NotifyPrefs        (user_id, guild_id)
  - Suggestions.Suggestions      (user_id, guild_id)
  - ServerData.Boosts            (user_id, guild_id)
  - ServerData.Boost_Events      (user_id, guild_id)
  - ServerData.Whitelist         (user_id, guild_id) - EXPORT ONLY, see below

Guild-scoped but keyed by ``id`` rather than ``user_id``:
  - ServerData.Members           (id, guild_id) - the member snapshot rows

Guild-scoped but keyed by the ACTOR rather than the subject:
  - Settings.AuditLog            (actor_id, guild_id) - EXPORT ONLY, see below

Not guild-scoped at all (join through ``suggestion_id`` to scope them):
  - Suggestions.Votes            (user_id, suggestion_id)
  - Suggestions.NotificationQueue(user_id, suggestion_id)

Account-wide, no guild dimension:
  - Suggestions.UserStats        (user_id) - full-scope delete/export only
  - Settings.UserPrivacy         (user_id) - EXPORT ONLY, see below

Shared content carrying the user only as attribution:
  - Daily.WYR                    (submitted_by) - the question bank. The question
    belongs to the server, so a delete only strips the attribution.

What is deliberately NOT deleted (owner rulings):
  - ServerData.Whitelist - a staff-authored moderation record. Exported so the
    member can see it, never removed by a member's own erasure request.
  - Settings.AuditLog - the admin audit trail. Exported where the member was the
    actor, never removed.
  - Settings.UserPrivacy - the opt-out preferences themselves must survive an
    erasure, or erasing your data would silently switch collection back on.
  - Anonymous suggestions - they store ``user_id: None`` and are unlinkable by
    design, so the ``user_id`` match below already skips them. Do not "improve"
    that by matching on anything else.
  - Daily.WYR ``approved_by`` / ``promoted_by`` - staff attribution, not the
    submitter's data.

Opting out is account-wide and forward-only: flipping a toggle stops future
collection and never deletes anything already stored. Erasure is the separate
delete_all path below.

Tag-tracker status is live Discord role membership, not user-owned data, so it
is neither exported nor deleted here.
"""

from __future__ import annotations

import time

from dashboard import db

#: The five opt-out toggles. ``all`` is the master switch; the rest are per feature.
PRIVACY_FEATURES: tuple[str, ...] = (
    "all",
    "wyr",
    "suggestions",
    "boosts",
    "member_snapshot",
)


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


def _default_features() -> dict[str, bool]:
    """Every toggle off - what a user with no stored document has."""
    return {name: False for name in PRIVACY_FEATURES}


def _normalize_features(stored: dict | None) -> dict[str, bool]:
    """Coerce a stored features map to exactly the five known booleans."""
    stored = stored or {}
    return {name: bool(stored.get(name, False)) for name in PRIVACY_FEATURES}


async def _guild_suggestion_ids(guild_id: int) -> list[str]:
    """Every suggestion id inside one guild.

    Suggestions.Votes and Suggestions.NotificationQueue carry no guild_id, so
    guild-scoping anything about them means joining through the suggestion. It is
    the whole guild's suggestions and not only the user's, because a member votes
    on other people's suggestions too. Restricting to ids the guild actually holds
    is what stops a scoped delete reaching into another server.
    """
    return await db.suggestions_suggestions().distinct(
        "suggestion_id", {"guild_id": str(guild_id)}
    )


def _wyr_question_match(user_id: int, guild_id: int | None) -> dict:
    """Match the bank questions this user submitted.

    A promoted question drops ``guild_id`` and keeps ``origin_guild_id``, so a
    guild-scoped view has to accept either or the submitter loses sight of their
    own question the moment it is promoted.
    """
    match: dict = {"submitted_by": str(user_id)}
    if guild_id is not None:
        match["$or"] = [
            {"guild_id": str(guild_id)},
            {"origin_guild_id": str(guild_id)},
        ]
    return match


async def distinct_guild_ids(user_id: int) -> set[str]:
    """Guild ids (as strings) where the user has any Codex data.

    This drives the privacy page's scope picker, so it has to cover every
    guild-scoped collection the export and delete reach. A guild missing here is a
    guild the member cannot scope an export or an erasure to, even though their
    data is sitting in it - so when a guild-scoped collection is added, add it here
    in the same pass.

    Suggestions.Votes and Suggestions.NotificationQueue are deliberately absent and
    that is NOT an oversight: neither carries a guild_id (the guild lives only on
    the suggestion document), so they contribute no guild of their own. A member
    who voted on somebody else's suggestion in a guild already sees that guild via
    the suggestion collections above, and the unscoped export and delete reach
    those votes in every case.
    """
    ids: set[str] = set()
    async for d in db.wyr_leaderboard().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.daily_wyr_votes().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.daily_wyr_submissions().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.daily_wyr_notify_prefs().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.suggestions_suggestions().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.serverdata_boosts().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.serverdata_boost_events().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    async for d in db.serverdata_whitelist().find({"user_id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    # ServerData.Members keys the member as `id`, not `user_id` - see the module
    # docstring. Querying user_id here would silently return nothing.
    async for d in db.serverdata_members().find({"id": str(user_id)}, {"guild_id": 1}):
        if d.get("guild_id") is not None:
            ids.add(str(d["guild_id"]))
    return ids


# ── Privacy preferences ──────────────────────────────────────────────────────


async def get_privacy(user_id: int) -> dict[str, bool]:
    """The user's opt-out toggles. No stored document means every toggle is off."""
    doc = await db.user_privacy().find_one({"user_id": str(user_id)})
    if not doc:
        return _default_features()
    return _normalize_features(doc.get("features"))


async def set_privacy(user_id: int, features: dict[str, bool]) -> dict[str, bool]:
    """Upsert the user's opt-out toggles and return what was saved.

    ``created_at`` is stamped on insert only, ``updated_at`` on every write, both
    as integer Unix seconds. Forward-only: this never touches collected data.
    """
    clean = _normalize_features(features)
    now = int(time.time())
    await db.user_privacy().update_one(
        {"user_id": str(user_id)},
        {
            "$set": {"features": clean, "updated_at": now},
            "$setOnInsert": {"user_id": str(user_id), "created_at": now},
        },
        upsert=True,
    )
    return clean


# ── Export ───────────────────────────────────────────────────────────────────


async def export_all(user_id: int, guild_id: int | None = None) -> dict:
    """Full dump of the user's Codex data, optionally scoped to one guild.

    Covers every collection that stores this user: the WYR leaderboard row, their
    individual WYR votes, their question submissions and notification preferences,
    the bank questions they wrote, their suggestions plus the votes and queued
    notifications attached to them, their account-wide suggestion stats, their
    boost record and boost event history, their member snapshot rows, their
    whitelist entries, the admin audit entries where they were the actor, and
    their own privacy preferences.

    Two of those are read-only inclusions that delete_all deliberately leaves
    alone - the whitelist (a staff moderation record) and the audit log (the admin
    trail). The privacy preferences are included too and also survive a delete.

    Account-wide collections (Suggestions.UserStats) are only included in a full,
    unscoped export; the privacy preferences are account-wide as well but are
    always included, because they describe the request itself rather than any
    guild's data.

    The bank questions are projected without the ``guilds`` map: that map is every
    server's aggregate vote counts for the question, which is other people's data
    and not the submitter's.
    """
    uid = str(user_id)
    gid = str(guild_id) if guild_id is not None else None

    wyr_match: dict = {"user_id": uid}
    sugg_match: dict = {"user_id": uid}
    boost_match: dict = {"user_id": uid}
    votes_match: dict = {"user_id": uid}
    submissions_match: dict = {"user_id": uid}
    notify_match: dict = {"user_id": uid}
    boost_events_match: dict = {"user_id": uid}
    whitelist_match: dict = {"user_id": uid}
    # ServerData.Members keys the member by `id`, not `user_id`.
    members_match: dict = {"id": uid}
    # Settings.AuditLog keys the admin who acted, not the subject of the action.
    audit_match: dict = {"actor_id": uid}
    if gid is not None:
        for match in (
            wyr_match, sugg_match, boost_match, votes_match, submissions_match,
            notify_match, boost_events_match, whitelist_match, members_match,
            audit_match,
        ):
            match["guild_id"] = gid

    wyr = [_strip(d) async for d in db.wyr_leaderboard().find(wyr_match)]
    wyr_votes = [_strip(d) async for d in db.daily_wyr_votes().find(votes_match)]
    wyr_submissions = [
        _strip(d) async for d in db.daily_wyr_submissions().find(submissions_match)
    ]
    wyr_notify_prefs = [
        _strip(d) async for d in db.daily_wyr_notify_prefs().find(notify_match)
    ]
    wyr_questions = [
        _strip(d)
        async for d in db.daily_wyr().find(
            _wyr_question_match(user_id, guild_id), {"guilds": 0}
        )
    ]
    suggestions = [_strip(d) async for d in db.suggestions_suggestions().find(sugg_match)]
    boosts = [_strip(d) async for d in db.serverdata_boosts().find(boost_match)]
    boost_events = [
        _strip(d) async for d in db.serverdata_boost_events().find(boost_events_match)
    ]
    member_snapshots = [_strip(d) async for d in db.serverdata_members().find(members_match)]
    whitelist_entries = [
        _strip(d) async for d in db.serverdata_whitelist().find(whitelist_match)
    ]
    audit_entries = [_strip(d) async for d in db.audit_log().find(audit_match)]

    # Suggestions.Votes / NotificationQueue carry no guild_id - scope them by
    # joining through the ids of suggestions that live in the requested guild.
    sugg_vote_match: dict = {"user_id": uid}
    sugg_notif_match: dict = {"user_id": uid}
    if guild_id is not None:
        scoped_ids = await _guild_suggestion_ids(guild_id)
        sugg_vote_match["suggestion_id"] = {"$in": scoped_ids}
        sugg_notif_match["suggestion_id"] = {"$in": scoped_ids}
    suggestion_votes = [_strip(d) async for d in db.suggestions_votes().find(sugg_vote_match)]
    suggestion_notifications = [
        _strip(d) async for d in db.suggestions_notification_queue().find(sugg_notif_match)
    ]

    # UserStats is account-wide (not guild-scoped); only include for full export.
    suggestion_stats = None
    if guild_id is None:
        doc = await db.suggestions_userstats().find_one({"user_id": uid})
        suggestion_stats = _strip(doc) if doc else None

    # Privacy preferences are account-wide but always included: they describe what
    # the user has asked Codex to stop collecting, in any scope.
    privacy_doc = await db.user_privacy().find_one({"user_id": uid})
    privacy_preferences = {
        "features": _normalize_features((privacy_doc or {}).get("features")),
        "created_at": (privacy_doc or {}).get("created_at"),
        "updated_at": (privacy_doc or {}).get("updated_at"),
        "stored": privacy_doc is not None,
    }

    return {
        "user_id": uid,
        "guild_id": gid,
        "wyr_leaderboard": wyr,
        "wyr_votes": wyr_votes,
        "wyr_submissions": wyr_submissions,
        "wyr_notify_prefs": wyr_notify_prefs,
        "wyr_questions_submitted": wyr_questions,
        "suggestions": suggestions,
        "suggestion_votes": suggestion_votes,
        "suggestion_notifications": suggestion_notifications,
        "suggestion_stats": suggestion_stats,
        "boosts": boosts,
        "boost_events": boost_events,
        "member_snapshots": member_snapshots,
        "whitelist_entries": whitelist_entries,
        "audit_log_entries": audit_entries,
        "privacy_preferences": privacy_preferences,
    }


# ── Delete ───────────────────────────────────────────────────────────────────


async def delete_all(user_id: int, guild_id: int | None = None) -> dict[str, int]:
    """Delete the user's Codex data. Optionally scoped to one guild.

    Removes the WYR leaderboard row, individual WYR votes, question submissions
    and notification preferences, suggestions (named ones only) with their votes
    and queued notifications, the boost record and boost event history, and the
    member snapshot rows. On the bank questions the user submitted, only the
    ``submitted_by`` attribution is unset - the question itself is the server's
    content and stays, as do the staff ``approved_by`` / ``promoted_by`` fields.

    Account-wide Suggestions.UserStats is only removed on a full (unscoped) delete.

    Deliberately untouched, per owner ruling: ServerData.Whitelist (staff-authored
    moderation record), Settings.AuditLog (admin trail), Settings.UserPrivacy (the
    opt-out must survive an erasure), and anonymous suggestions, which store
    ``user_id: None`` and are therefore already outside every match below.

    Returns a per-collection count. ``wyr_questions_unattributed`` is a modified
    count (documents kept, attribution stripped), not a deleted count.
    """
    uid = str(user_id)
    gid = str(guild_id) if guild_id is not None else None

    wyr_match: dict = {"user_id": uid}
    sugg_match: dict = {"user_id": uid}
    boost_match: dict = {"user_id": uid}
    votes_match: dict = {"user_id": uid}
    submissions_match: dict = {"user_id": uid}
    notify_match: dict = {"user_id": uid}
    boost_events_match: dict = {"user_id": uid}
    members_match: dict = {"id": uid}
    if gid is not None:
        for match in (
            wyr_match, sugg_match, boost_match, votes_match, submissions_match,
            notify_match, boost_events_match, members_match,
        ):
            match["guild_id"] = gid

    # Suggestion votes / notifications before the suggestions themselves: once the
    # suggestion documents are gone there is no guild left to join through.
    sugg_vote_match: dict = {"user_id": uid}
    sugg_notif_match: dict = {"user_id": uid}
    if guild_id is not None:
        scoped_ids = await _guild_suggestion_ids(guild_id)
        sugg_vote_match["suggestion_id"] = {"$in": scoped_ids}
        sugg_notif_match["suggestion_id"] = {"$in": scoped_ids}

    deleted: dict[str, int] = {}
    deleted["wyr_leaderboard"] = (
        await db.wyr_leaderboard().delete_many(wyr_match)
    ).deleted_count
    deleted["wyr_votes"] = (
        await db.daily_wyr_votes().delete_many(votes_match)
    ).deleted_count
    deleted["wyr_submissions"] = (
        await db.daily_wyr_submissions().delete_many(submissions_match)
    ).deleted_count
    deleted["wyr_notify_prefs"] = (
        await db.daily_wyr_notify_prefs().delete_many(notify_match)
    ).deleted_count
    deleted["wyr_questions_unattributed"] = (
        await db.daily_wyr().update_many(
            _wyr_question_match(user_id, guild_id), {"$unset": {"submitted_by": ""}}
        )
    ).modified_count
    deleted["suggestion_votes"] = (
        await db.suggestions_votes().delete_many(sugg_vote_match)
    ).deleted_count
    deleted["suggestion_notifications"] = (
        await db.suggestions_notification_queue().delete_many(sugg_notif_match)
    ).deleted_count
    deleted["suggestions"] = (
        await db.suggestions_suggestions().delete_many(sugg_match)
    ).deleted_count
    deleted["boosts"] = (
        await db.serverdata_boosts().delete_many(boost_match)
    ).deleted_count
    deleted["boost_events"] = (
        await db.serverdata_boost_events().delete_many(boost_events_match)
    ).deleted_count
    deleted["member_snapshots"] = (
        await db.serverdata_members().delete_many(members_match)
    ).deleted_count
    if guild_id is None:
        deleted["suggestion_stats"] = (
            await db.suggestions_userstats().delete_many({"user_id": uid})
        ).deleted_count
    return deleted
