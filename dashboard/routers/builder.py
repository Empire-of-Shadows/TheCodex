"""Builder API routes - GET/PUT guide, greeting & board data per guild."""

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
from Features.NewMembers.greeting_schema import validate_greeting_schema  # noqa: E402
from Features.Board.board_schema import validate_board_schema  # noqa: E402

logger = get_logger("dashboard.routers.builder")

router = APIRouter(tags=["builder"])

# Boards are keyed by (guild_id, board_id). One board per guild today; the key
# leaves room for more without a storage change.
_DEFAULT_BOARD_ID = "main"


class GuidePutBody(BaseModel):
    guide_data: dict = Field(..., description="Guide payload (pages, components)")


class GreetingPutBody(BaseModel):
    greeting_data: dict = Field(..., description="Greeting payload (components, accent_color)")


class BoardPutBody(BaseModel):
    board_data: dict = Field(..., description="Board payload (components, responses, accent_color)")


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


# ── Greeting ──────────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/greeting")
async def get_greeting(guild_id: str, _session: dict = Depends(require_guild_admin)):
    """Fetch greeting components from GuildConfig."""
    doc = await db.guild_config().find_one({"guild_id": str(int(guild_id))})
    if doc is None:
        return {"greeting_data": None}
    new_members = doc.get("new_members", {})
    components = new_members.get("greeting_components")
    return {"greeting_data": components}


@router.put("/guilds/{guild_id}/greeting")
async def put_greeting(
    guild_id: str,
    body: GreetingPutBody,
    session: dict = Depends(require_guild_admin),
):
    """Validate and save greeting components for a guild."""
    greeting_data = body.greeting_data
    ok, error = validate_greeting_schema(greeting_data)
    if not ok:
        raise HTTPException(status_code=422, detail=error)

    user_id = int(session["user_data"]["id"])
    logger.info("Saving greeting for guild %s by user %s", guild_id, user_id)
    # upsert + guild_id in $set so the save still lands if the config doc was
    # never seeded (or was removed by guild-data cleanup) - matches put_guide.
    await db.guild_config().update_one(
        {"guild_id": str(int(guild_id))},
        {"$set": {
            "guild_id": str(int(guild_id)),
            "new_members.greeting_components": greeting_data,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return {"ok": True}


# ── Info Board ────────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/board")
async def get_board(guild_id: str, _session: dict = Depends(require_guild_admin)):
    """Fetch board data for a guild, plus where it is currently posted."""
    doc = await db.board_content().find_one(
        {"guild_id": str(int(guild_id)), "board_id": _DEFAULT_BOARD_ID}
    )
    if doc is None:
        return {"board_data": None, "posted": None}
    return {
        "board_data": doc.get("board_data"),
        # Read-only context for the builder: it can say where the board lives,
        # but posting and moving stay in the admin panel
        # (/admin panel -> Info Board -> Post / Update Board).
        "posted": {
            "channel_id": doc.get("channel_id"),
            "message_id": doc.get("message_id"),
        } if doc.get("message_id") else None,
    }


@router.put("/guilds/{guild_id}/board")
async def put_board(
    guild_id: str,
    body: BoardPutBody,
    session: dict = Depends(require_guild_admin),
):
    """Validate and save board data for a guild.

    Deliberately does not touch channel_id / message_id: editing the layout must
    not lose track of where the board is already posted. The saved layout goes
    live when someone uses the admin panel's Info Board -> Post / Update Board
    screen.
    """
    board_data = body.board_data
    ok, error = validate_board_schema(board_data)
    if not ok:
        raise HTTPException(status_code=422, detail=error)

    user_id = int(session["user_data"]["id"])
    logger.info("Saving board for guild %s by user %s", guild_id, user_id)
    await db.board_content().update_one(
        {"guild_id": str(int(guild_id)), "board_id": _DEFAULT_BOARD_ID},
        {"$set": {
            "guild_id": str(int(guild_id)),
            "board_id": _DEFAULT_BOARD_ID,
            "board_data": board_data,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": str(user_id),
        }},
        upsert=True,
    )
    return {"ok": True}
