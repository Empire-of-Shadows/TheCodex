"""Guild overview API - everything the admin home renders, in one round trip.

Gated on ``require_panel_access``, the same tier the settings page uses: a
Panel Access role is enough, live MANAGE_GUILD is not required.

Read-only. The six sections are built concurrently and EACH one is allowed to
fail on its own - a section that raises is logged and returned as ``null``,
which is exactly why every section is nullable in the frontend contract. One
broken collection must not blank the page.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from dashboard import db
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import require_panel_access
from dashboard.services import overview as overview_service
from storage.log import get_logger

logger = get_logger("dashboard.routers.overview")

router = APIRouter(tags=["overview"])

#: Section name -> the key it occupies in the response, in gather order.
_SECTIONS = ("wyr", "suggestions", "members", "drops", "content", "trackers", "feature_usage")


@router.get("/guilds/{guild_id}/overview")
async def guild_overview(guild_id: str, session: dict = Depends(get_current_user)):
    """Return a ``GuildOverview`` for one guild."""
    await require_panel_access(session, guild_id)
    # Validate as a snowflake, query by the canonical string form - every stored
    # id is a string since migration m4, and an int matches nothing silently.
    gid = str(int(guild_id))

    config_doc = await db.guild_config().find_one({"guild_id": gid}) or {}

    results = await asyncio.gather(
        overview_service.build_wyr(gid, config_doc),
        overview_service.build_suggestions(gid, config_doc),
        overview_service.build_members(gid),
        overview_service.build_drops(gid, config_doc),
        overview_service.build_content(gid, config_doc),
        overview_service.build_trackers(gid, config_doc),
        overview_service.build_feature_usage(gid),
        return_exceptions=True,
    )

    sections: dict[str, dict | None] = {}
    for name, result in zip(_SECTIONS, results):
        if isinstance(result, BaseException):
            logger.warning(
                "Overview section '%s' failed for guild %s", name, gid,
                exc_info=result,
            )
            sections[name] = None
        else:
            sections[name] = result

    try:
        features = overview_service.build_features(config_doc, **sections)
    except Exception:
        # features is not nullable in the contract, so an empty rail is the only
        # shape available here. It is logged loudly because an empty rail on a
        # configured guild is a bug, not a state the data can produce.
        logger.error("Overview feature rail failed for guild %s", gid, exc_info=True)
        features = []

    return {"guild_id": gid, "features": features, **sections}
