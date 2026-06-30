"""Audit Log read endpoint - admin-only.

The bot writes audit entries to Settings.AuditLog via storage/audit_log.py
on every successful admin-driven config mutation. This router exposes those
entries to admins (admin tier only; mods are excluded).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard import db
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import require_panel_access
from storage.logging import get_logger

logger = get_logger("dashboard.routers.audit_log")

router = APIRouter(tags=["audit_log"])


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
        gid = int(guild_id)
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
