"""Create a role or a channel from the settings page (added 2026-11-20).

The dashboard half of the admin panel's inline Create button: every role and
channel picker on the settings page can create what it needs on the spot, when the
bot holds the permission Discord requires. The rules (permissions, name rules,
Discord's limits) live in the engine, ``dashboard/_engine/discord_objects.py``.

Same access as the settings form these buttons sit on: the admin tier, live
Manage Server or a Panel Access role, which is also who can create from the panel.
Creating saves no setting; the page selects the new role or channel and the
person saves the section. Every create is recorded in the change history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dashboard import db
from dashboard._engine import discord_objects as objects
from dashboard._engine.rate_limit import rate_limit_dependency
from dashboard.auth.panel_role import require_guild_admin
from dashboard.config import BOT_TOKEN
from storage.log import get_logger

logger = get_logger("dashboard.routers.discord_objects")

router = APIRouter(tags=["discord-objects"])

# Per IP. Creating is a deliberate click; this only stops a stuck button or a
# script from filling a server with channels.
_create_limit = rate_limit_dependency("discord_create", 10, 60)


class RoleCreate(BaseModel):
    name: str = Field(..., max_length=200)


class ChannelCreate(BaseModel):
    name: str = Field(..., max_length=200)
    kind: Literal["text", "voice", "category"] = "text"
    parent_id: Optional[str] = Field(default=None, max_length=32)


def _guild_id(guild_id: str) -> str:
    try:
        return str(int(guild_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid server id")


def _actor(session: dict) -> tuple[Optional[str], str]:
    user_data = session.get("user_data") or {}
    actor_id = user_data.get("id") or session.get("user_id")
    actor_name = (
        user_data.get("global_name")
        or user_data.get("username")
        or str(actor_id or "unknown")
    )
    return (str(actor_id) if actor_id is not None else None), str(actor_name)[:128]


async def _audit(gid: str, session: dict, key: str, created: dict) -> None:
    actor_id, actor_name = _actor(session)
    if actor_id is None:
        return
    try:
        await db.audit_log().insert_one({
            "guild_id": gid,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "source": "dashboard",
            "section": "discord",
            "key": key,
            "old_value": None,
            "new_value": {"id": created["id"], "name": created["name"]},
            "action": "create",
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        logger.warning("Audit log write failed for guild %s", gid, exc_info=True)


def _require_token() -> None:
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Bot token not configured")


@router.get("/guilds/{guild_id}/create-abilities")
async def create_abilities(guild_id: str, _session: dict = Depends(require_guild_admin)):
    """What the bot may create in this server, for the Create buttons."""
    _require_token()
    return await objects.create_abilities(_guild_id(guild_id))


@router.post("/guilds/{guild_id}/roles", status_code=201, dependencies=[Depends(_create_limit)])
async def create_role(
    guild_id: str,
    body: RoleCreate,
    session: dict = Depends(require_guild_admin),
):
    _require_token()
    gid = _guild_id(guild_id)
    _, actor_name = _actor(session)
    try:
        role = await objects.create_role(
            gid, body.name, reason=f"Dashboard: created by {actor_name}",
        )
    except objects.CreateRefused as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    await _audit(gid, session, "discord.role", role)
    return role


@router.post("/guilds/{guild_id}/channels", status_code=201, dependencies=[Depends(_create_limit)])
async def create_channel(
    guild_id: str,
    body: ChannelCreate,
    session: dict = Depends(require_guild_admin),
):
    _require_token()
    gid = _guild_id(guild_id)
    _, actor_name = _actor(session)
    try:
        channel = await objects.create_channel(
            gid,
            body.name,
            kind=body.kind,
            parent_id=body.parent_id or None,
            reason=f"Dashboard: created by {actor_name}",
        )
    except objects.CreateRefused as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    await _audit(gid, session, f"discord.{body.kind}_channel" if body.kind != "category" else "discord.category", channel)
    return channel
