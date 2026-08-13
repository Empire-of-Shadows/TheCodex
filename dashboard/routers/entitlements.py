"""Member entitlements API - what the logged-in user can use in one guild."""

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import resolve_panel_role
from dashboard.routers.dashboard import _fetch_bot_guild_ids
from dashboard.services.entitlements import get_entitlements
from storage.log import get_logger

logger = get_logger("dashboard.routers.entitlements")

router = APIRouter(tags=["entitlements"])


@router.get("/user-entitlements")
async def user_entitlements(
    guild_id: str = Query(...),
    session: dict = Depends(get_current_user),
):
    """The member's entitlements in one guild. Any logged-in member of it may ask.

    Guild-scoped by necessity: every rule resolves against that guild's config
    and the member's roles there. The same membership check as /user-activity
    keeps an authenticated user from probing servers they are not in.
    """
    session_guild_ids = {g["id"] for g in session.get("guilds", [])}
    if guild_id not in session_guild_ids:
        raise HTTPException(
            status_code=404,
            detail="You are not a member of this guild (or session is stale).",
        )
    if guild_id not in await _fetch_bot_guild_ids():
        raise HTTPException(status_code=404, detail="Bot is not in this guild.")

    panel_role = await resolve_panel_role(session, guild_id, verify_manage_live=False)
    user_id = session["user_data"]["id"]
    return await get_entitlements(guild_id, user_id, panel_role == "admin")
