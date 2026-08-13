"""User-scoped data API: the logged-in user's privacy toggles, export and delete."""

import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

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


@router.get("/user/data/guilds", summary="Guilds where the user has Codex data")
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


# ── Privacy preferences ──────────────────────────────────────────────────────


class PrivacyFeatures(BaseModel):
    """The five data-collection opt-out toggles. Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    all: bool = False
    wyr: bool = False
    suggestions: bool = False
    boosts: bool = False
    member_snapshot: bool = False


@router.get("/user/privacy", summary="The logged-in user's data-collection opt-outs")
async def get_privacy(session: dict = Depends(get_current_user)):
    """Read the user's opt-out toggles.

    Every toggle defaults to false when the user has never saved a preference, so
    a first visit returns all five as false rather than 404ing.
    """
    user_id = int(session["user_data"]["id"])
    return {"features": await user_data.get_privacy(user_id)}


@router.put("/user/privacy", summary="Save the logged-in user's data-collection opt-outs")
async def put_privacy(
    features: PrivacyFeatures = Body(..., embed=True),
    session: dict = Depends(get_current_user),
):
    """Save the user's opt-out toggles and return what was stored.

    The body is the same envelope the GET returns - ``{"features": {...}}`` - not a
    bare toggle map, so a client can round-trip what it just read. Unknown toggles
    inside ``features`` are rejected.

    Opting out is account-wide and forward-only: it stops Codex collecting new
    data in every server, and never deletes anything already stored. Use
    DELETE /user/data for erasure.
    """
    user_id = int(session["user_data"]["id"])
    saved = await user_data.set_privacy(user_id, features.model_dump())
    return {"features": saved}


# ── Export / delete ──────────────────────────────────────────────────────────


@router.get("/user/data/export", summary="Download everything Codex stores about the user")
async def export_data(
    guild_id: str | None = Query(None),
    session: dict = Depends(get_current_user),
):
    """Download the user's Codex data as a JSON attachment, optionally one guild only.

    Includes their WYR leaderboard row, individual WYR votes, question submissions,
    WYR notification preferences, the bank questions they submitted, their
    suggestions with the votes and queued notifications attached to them, their
    account-wide suggestion stats (full export only), their boost record and boost
    event history, their member snapshot rows, their whitelist entries, the admin
    audit entries where they were the actor, and their own privacy preferences.

    Whitelist entries, audit entries and privacy preferences are read-only
    inclusions: they appear here but are never removed by the delete route.
    """
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


@router.delete("/user/data", summary="Erase the user's Codex data")
async def delete_data(
    body: DeleteRequest,
    session: dict = Depends(get_current_user),
):
    """Erase the user's Codex data, optionally in one guild only.

    Must be confirmed by sending ``{confirm: true}``.

    Removes their WYR leaderboard row, WYR votes, question submissions and
    notification preferences, their suggestions with the votes and queued
    notifications attached to them, their suggestion stats (full erasure only),
    their boost record and boost event history, and their member snapshot rows.
    Bank questions they submitted stay - they are the server's content now - but
    the submitter attribution is stripped from them.

    Kept on purpose: whitelist entries (a staff moderation record), admin audit
    entries, the privacy preferences themselves (an erasure must not switch data
    collection back on), and anonymous suggestions, which store no user id at all.

    The returned counts are per collection; ``wyr_questions_unattributed`` counts
    questions kept with the attribution removed, not questions deleted.
    """
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
