"""Public, unauthenticated ecosystem stats for the login hero teaser.

Cheap aggregate counts cached for 5 minutes so a login traffic spike collapses
to a single Mongo aggregation per stat per worker per 5 min.
"""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard import db
from storage.logging import get_logger

logger = get_logger("dashboard.routers.public_stats")

router = APIRouter(tags=["public-stats"])

_CACHE_TTL = 300.0
_cache: dict[str, object] = {"data": None, "ts": 0.0}


async def _compute() -> dict[str, int]:
    servers = await db.guild_config().count_documents({})
    suggestions = await db.suggestions_suggestions().count_documents({})

    wyr_votes = 0
    agg = await db.wyr_leaderboard().aggregate([
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total_votes", 0]}}}}
    ])
    async for doc in agg:
        wyr_votes += int(doc.get("total") or 0)

    return {
        "servers": int(servers),
        "suggestions": int(suggestions),
        "wyr_votes": int(wyr_votes),
    }


@router.get("/stats/public")
async def public_stats():
    now = time.monotonic()
    data = _cache["data"]
    if data is None or now - float(_cache["ts"]) >= _CACHE_TTL:
        try:
            data = await _compute()
            _cache["data"] = data
            _cache["ts"] = now
        except Exception:
            logger.warning("public_stats compute failed", exc_info=True)
            if data is None:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "stats unavailable"},
                )
    return JSONResponse(
        content=data,
        headers={"Cache-Control": "public, max-age=60"},
    )