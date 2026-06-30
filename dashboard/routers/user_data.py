"""User-scoped data API: export and delete the logged-in user's Codex data."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dashboard.auth.dependencies import get_current_user
from dashboard.services import user_data

router = APIRouter(tags=["user-data"])


def _resolve_scope(session: dict, guild_id: str | None) -> int | None:
    """Validate an optional guild_id against session membership. Returns int or None."""
    if not guild_id:
        return None
    try:
        gid = int(guild_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid guild_id")
    member = any(str(g.get("id")) == str(guild_id) for g in session.get("guilds", []))
    if not member:
        raise HTTPException(
            status_code=404,
            detail="You are not a member of this guild (or session is stale).",
        )
    return gid


@router.get("/user/data/guilds")
async def user_data_guilds(session: dict = Depends(get_current_user)):
    """Guilds where the user has Codex data, for the privacy scope picker."""
    user_id = int(session["user_data"]["id"])
    ids = await user_data.distinct_guild_ids(user_id)
    name_map = {str(g["id"]): g for g in session.get("guilds", [])}
    return [
        {
            "id": gid,
            "name": name_map.get(gid, {}).get("name"),
            "icon": name_map.get(gid, {}).get("icon"),
        }
        for gid in ids
    ]


@router.get("/user/data/export")
async def export_data(
    guild_id: str | None = Query(None),
    session: dict = Depends(get_current_user),
):
    user_id = int(session["user_data"]["id"])
    gid = _resolve_scope(session, guild_id)
    payload = await user_data.export_all(user_id, gid)
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")

    suffix = f"-guild-{gid}" if gid is not None else ""
    filename = f"the-codex-data-{user_id}{suffix}.json"
    return StreamingResponse(
        iter([body]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class DeleteRequest(BaseModel):
    confirm: bool = False
    guild_id: str | None = None


@router.delete("/user/data")
async def delete_data(
    body: DeleteRequest,
    session: dict = Depends(get_current_user),
):
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Delete must be confirmed by sending {confirm: true}.",
        )
    user_id = int(session["user_data"]["id"])
    gid = _resolve_scope(session, body.guild_id)
    deleted = await user_data.delete_all(user_id, gid)
    return {
        "user_id": str(user_id),
        "guild_id": str(gid) if gid is not None else None,
        "deleted": deleted,
    }
