"""Builder API routes - GET/PUT guide & welcome data per guild."""

import os
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dashboard import db
from dashboard.auth.panel_role import require_guild_admin
from storage.log import get_logger

# Make project-root feature modules importable (Features.* lives above dashboard/).
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from Features.Guide.guide_schema import (  # noqa: E402
    normalize_pages,
    validate_guide_schema,
)
from Features.NewMembers.welcome_schema import validate_welcome_schema  # noqa: E402

logger = get_logger("dashboard.routers.builder")

router = APIRouter(tags=["builder"])


class GuidePutBody(BaseModel):
    guide_data: dict = Field(..., description="Guide payload (pages, components)")


class WelcomePutBody(BaseModel):
    welcome_data: dict = Field(..., description="Welcome payload (components, accent_color)")


# ── Guide ─────────────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/guide")
async def get_guide(guild_id: str, _session: dict = Depends(require_guild_admin)):
    """Fetch guide data for a guild."""
    doc = await db.guide_content().find_one({"guild_id": str(int(guild_id))})
    if doc is None:
        return {"guide_data": None}
    return {"guide_data": doc.get("guide_data")}


@router.put("/guilds/{guild_id}/guide")
async def put_guide(
    guild_id: str,
    body: GuidePutBody,
    session: dict = Depends(require_guild_admin),
):
    """Validate and save guide data for a guild."""
    guide_data = normalize_pages(body.guide_data)
    ok, error = validate_guide_schema(guide_data)
    if not ok:
        raise HTTPException(status_code=422, detail=error)

    user_id = int(session["user_data"]["id"])
    logger.info("Saving guide for guild %s by user %s", guild_id, user_id)
    await db.guide_content().update_one(
        {"guild_id": str(int(guild_id))},
        {"$set": {
            "guild_id": str(int(guild_id)),
            "guide_data": guide_data,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": str(user_id),
        }},
        upsert=True,
    )
    return {"ok": True, "guide_data": guide_data}


# ── Welcome ───────────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/welcome")
async def get_welcome(guild_id: str, _session: dict = Depends(require_guild_admin)):
    """Fetch welcome components from GuildConfig."""
    doc = await db.guild_config().find_one({"guild_id": str(int(guild_id))})
    if doc is None:
        return {"welcome_data": None}
    new_members = doc.get("new_members", {})
    components = new_members.get("welcome_components")
    return {"welcome_data": components}


@router.put("/guilds/{guild_id}/welcome")
async def put_welcome(
    guild_id: str,
    body: WelcomePutBody,
    session: dict = Depends(require_guild_admin),
):
    """Validate and save welcome components for a guild."""
    welcome_data = body.welcome_data
    ok, error = validate_welcome_schema(welcome_data)
    if not ok:
        raise HTTPException(status_code=422, detail=error)

    user_id = int(session["user_data"]["id"])
    logger.info("Saving welcome for guild %s by user %s", guild_id, user_id)
    # upsert + guild_id in $set so the save still lands if the config doc was
    # never seeded (or was removed by guild-data cleanup) - matches put_guide.
    await db.guild_config().update_one(
        {"guild_id": str(int(guild_id))},
        {"$set": {
            "guild_id": str(int(guild_id)),
            "new_members.welcome_components": welcome_data,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return {"ok": True}
