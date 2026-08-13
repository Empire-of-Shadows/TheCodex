"""Audit Log read endpoint - admin-only.

The bot writes audit entries to Settings.AuditLog via the engine AuditLog service
on every successful admin-driven config mutation. This router exposes those
entries to admins (admin tier only; mods are excluded).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard import db
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import require_panel_access
from storage.log import get_logger

logger = get_logger("dashboard.routers.audit_log")

router = APIRouter(tags=["audit_log"])

# The AuditLog TTL is declared bot side in storage/settings/collections.py (index
# `created_at_ttl`, expireAfterSeconds=31536000). It is mirrored here as whole days
# so the dashboard can state how long history is kept without importing the bot's
# collection registry, which builds db_manager at import time.
AUDIT_RETENTION_SECONDS = 31_536_000
AUDIT_RETENTION_DAYS = AUDIT_RETENTION_SECONDS // 86_400


def _serialize(doc: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif k in ("guild_id", "actor_id") and isinstance(v, int):
            out[k] = str(v)
        else:
            out[k] = v
    return out


@router.get("/guilds/{guild_id}/audit-log")
async def list_audit_log(
    guild_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None, description="ISO timestamp cursor"),
    section: str | None = Query(None),
    session: dict = Depends(get_current_user),
):
    role = await require_panel_access(session, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Audit log is admin-only")

    try:
        # Validate as a snowflake; the collection is string-keyed (migration m8).
        gid = str(int(guild_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid guild_id")

    query: dict = {"guild_id": gid}
    if before:
        try:
            query["created_at"] = {"$lt": datetime.fromisoformat(before)}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'before' timestamp")
    if section:
        query["section"] = section

    cursor = (
        db.audit_log()
        .find(query)
        .sort("created_at", -1)
        .limit(limit + 1)
    )
    docs = [doc async for doc in cursor]
    has_more = len(docs) > limit
    docs = docs[:limit]
    next_cursor = (
        docs[-1]["created_at"].isoformat()
        if has_more and docs and isinstance(docs[-1].get("created_at"), datetime)
        else None
    )
    return {
        "entries": [_serialize(d) for d in docs],
        "next_cursor": next_cursor,
    }


@router.get("/guilds/{guild_id}/audit-log/summary")
async def audit_log_summary(
    guild_id: str,
    session: dict = Depends(get_current_user),
):
    """Totals behind the change history, for the summary tile above the table.

    Same gate as the listing route above - admin tier only. One aggregation, so
    the tile costs a single round trip: how many entries are held, where they came
    from, which settings section they touched, how many distinct people are
    represented, and the oldest entry still kept.
    """
    role = await require_panel_access(session, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Audit log is admin-only")

    try:
        # Validate as a snowflake; the collection is string-keyed (migration m8).
        gid = str(int(guild_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid guild_id")

    cursor = await db.audit_log().aggregate([
        {"$match": {"guild_id": gid}},
        {
            "$facet": {
                "total": [{"$count": "n"}],
                "by_source": [{"$group": {"_id": "$source", "n": {"$sum": 1}}}],
                "by_section": [{"$group": {"_id": "$section", "n": {"$sum": 1}}}],
                "actors": [{"$group": {"_id": "$actor_id"}}, {"$count": "n"}],
                "oldest": [{"$group": {"_id": None, "at": {"$min": "$created_at"}}}],
            }
        },
    ])
    rows = [doc async for doc in cursor]
    # $facet emits one document even when nothing matched (every sub-pipeline just
    # returns an empty array), so this is a guard rather than an expected branch -
    # a guild with no entries still has to answer 0, not 500.
    facets: dict[str, Any] = rows[0] if rows else {}

    def _counts(facet: str) -> dict[str, int]:
        # An entry written without that field groups under None. It is still a
        # real change, so it is counted under "unknown" rather than dropped.
        out: dict[str, int] = {}
        for row in facets.get(facet) or []:
            out[str(row.get("_id") or "unknown")] = int(row.get("n") or 0)
        return out

    total_rows = facets.get("total") or []
    actor_rows = facets.get("actors") or []
    oldest_rows = facets.get("oldest") or []
    oldest_at = oldest_rows[0].get("at") if oldest_rows else None

    return {
        "total": int(total_rows[0].get("n") or 0) if total_rows else 0,
        "by_source": _counts("by_source"),
        "by_section": _counts("by_section"),
        "distinct_actors": int(actor_rows[0].get("n") or 0) if actor_rows else 0,
        "oldest_at": oldest_at.isoformat() if isinstance(oldest_at, datetime) else None,
        "retention_days": AUDIT_RETENTION_DAYS,
    }
