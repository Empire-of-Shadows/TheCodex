"""Builder API routes — GET/PUT guide & welcome data per guild."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from dashboard import db
from dashboard.auth.dependencies import get_current_user, require_guild_access

router = APIRouter(tags=["builder"])


# ── Guide ─────────────────────────────────────────────────────────────────

@router.get("/guilds/{guild_id}/guide")
async def get_guide(guild_id: str, session: dict = Depends(get_current_user)):
    """Fetch guide data for a guild."""
    require_guild_access(session, guild_id)
    doc = await db.guide_content().find_one({"guild_id": int(guild_id)})
    if doc is None:
        return {"guide_data": None}
    return {"guide_data": doc.get("guide_data")}


@router.put("/guilds/{guild_id}/guide")
async def put_guide(guild_id: str, body: dict, session: dict = Depends(get_current_user)):
    """Validate and save guide data for a guild."""
    require_guild_access(session, guild_id)

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from Features.Guide.guide_schema import validate_guide_schema, normalize_pages

    guide_data = body.get("guide_data")
    if guide_data is None:
        raise HTTPException(status_code=422, detail="Missing guide_data")

    # Normalize (auto-generate IDs) then validate
    guide_data = normalize_pages(guide_data)
    ok, error = validate_guide_schema(guide_data)
    if not ok:
        raise HTTPException(status_code=422, detail=error)

    user_id = int(session["user_data"]["id"])
    await db.guide_content().update_one(
        {"guild_id": int(guild_id)},
        {"$set": {
            "guild_id": int(guild_id),
            "guide_data": guide_data,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": user_id,
        }},
        upsert=True,
    )
    return {"ok": True, "guide_data": guide_data}


# ── Welcome ───────────────────────────────────────────────────────────────

@router.get("/guilds/{guild_id}/welcome")
async def get_welcome(guild_id: str, session: dict = Depends(get_current_user)):
    """Fetch welcome components from GuildConfig."""
    require_guild_access(session, guild_id)
    doc = await db.guild_config().find_one({"guild_id": int(guild_id)})
    if doc is None:
        return {"welcome_data": None}
    new_members = doc.get("new_members", {})
    components = new_members.get("welcome_components")
    return {"welcome_data": components}


@router.put("/guilds/{guild_id}/welcome")
async def put_welcome(guild_id: str, body: dict, session: dict = Depends(get_current_user)):
    """Validate and save welcome components for a guild."""
    require_guild_access(session, guild_id)

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from Features.NewMembers.welcome_schema import validate_welcome_schema

    welcome_data = body.get("welcome_data")
    if welcome_data is None:
        raise HTTPException(status_code=422, detail="Missing welcome_data")

    ok, error = validate_welcome_schema(welcome_data)
    if not ok:
        raise HTTPException(status_code=422, detail=error)

    await db.guild_config().update_one(
        {"guild_id": int(guild_id)},
        {"$set": {
            "new_members.welcome_components": welcome_data,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"ok": True}
