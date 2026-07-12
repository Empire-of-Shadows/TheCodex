"""Per-guild settings GET/PUT — reads + writes Settings.GuildConfig.

Mirrors the panel groups defined in commands/admin/panel_configs.py but
exposes them through a single section-keyed JSON endpoint suitable for
the web dashboard. Admin tier may edit every mutable section; mod tier
is gated to MOD_ALLOWED_SECTIONS (currently empty).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dashboard import db
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import require_panel_access
from storage.logging import get_logger

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from storage.config_manager import DEFAULT_CONFIG  # noqa: E402

logger = get_logger("dashboard.routers.settings")

router = APIRouter(tags=["settings"])

# Sections the dashboard may mutate. welcome_components is intentionally
# excluded — the builder route owns that field. embed is also excluded
# from the simple settings form (managed via Discord panel for now).
_MUTABLE_SECTIONS: frozenset[str] = frozenset({
    "roles",
    "server",
    "wyr",
    "new_members",
    "announcement",
    "tag_tracker",
    "drops",
    "suggestions",
    "boost",
    "guide",
})

# Sections a mod tier may PUT. Empty until features opt in.
MOD_ALLOWED_SECTIONS: frozenset[str] = frozenset()

# Subkeys that exist inside a section's stored doc but are NOT managed by
# the settings dashboard. Stripped from GET responses (so the frontend draft
# does not include them) and excluded from PUT allowed-keys (so an honest
# client can never reintroduce them).
_SECTION_EXCLUDED_KEYS: dict[str, frozenset[str]] = {
    # welcome_components is owned by the builder route.
    "new_members": frozenset({"welcome_components"}),
    # tiers is the color-tier mapping; managed via the Discord /admin panel.
    "roles": frozenset({"tiers"}),
}

# ── ID coercion ─────────────────────────────────────────────────────────────
#
# Discord snowflakes exceed JS Number safe range. Stringify on the way out,
# coerce back to int on the way in.

_CHANNEL_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "server": ("admin_channel_id",),
    "wyr": ("channel_id",),
    "new_members": ("welcome_channel_id",),
    "announcement": ("channel_id",),
    "drops": ("channel_id",),
    "suggestions": ("channel_id",),
    "boost": ("channel_id",),
    "guide": ("channel_id",),
}

_ROLE_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "wyr": ("ping_role_id",),
    "new_members": ("whitelist_role_id",),
    "drops": ("manager_role_id",),
    "tag_tracker": ("role_id",),
}

_ROLE_ID_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "roles": ("admin_role_ids", "mod_role_ids"),
}


def _stringify_id(v: Any) -> Any:
    return str(v) if isinstance(v, int) else v


def _coerce_id(v: Any) -> Any:
    if v is None or isinstance(v, int):
        return v
    if isinstance(v, str) and v.lstrip("-").isdigit():
        try:
            return int(v)
        except ValueError:
            return v
    return v


def _serialize_section(section: str, value: dict) -> dict:
    """Stringify snowflake IDs inside one section."""
    out = dict(value)
    for k in _CHANNEL_ID_FIELDS.get(section, ()):
        if out.get(k) is not None:
            out[k] = _stringify_id(out[k])
    for k in _ROLE_ID_FIELDS.get(section, ()):
        if out.get(k) is not None:
            out[k] = _stringify_id(out[k])
    for k in _ROLE_ID_LIST_FIELDS.get(section, ()):
        if isinstance(out.get(k), list):
            out[k] = [_stringify_id(v) for v in out[k]]
    # drops.tracker_channels is a dict of name -> snowflake
    if section == "drops" and isinstance(out.get("tracker_channels"), dict):
        out["tracker_channels"] = {
            k: _stringify_id(v) if v is not None else None
            for k, v in out["tracker_channels"].items()
        }
    return out


def _coerce_section_ids(section: str, value: dict) -> None:
    for k in _CHANNEL_ID_FIELDS.get(section, ()):
        if k in value:
            value[k] = _coerce_id(value[k])
    for k in _ROLE_ID_FIELDS.get(section, ()):
        if k in value:
            value[k] = _coerce_id(value[k])
    for k in _ROLE_ID_LIST_FIELDS.get(section, ()):
        if k in value and isinstance(value[k], list):
            value[k] = [_coerce_id(v) for v in value[k]]
    if section == "drops" and isinstance(value.get("tracker_channels"), dict):
        value["tracker_channels"] = {
            k: _coerce_id(v) for k, v in value["tracker_channels"].items()
        }


def _section_from_doc(section: str, doc: dict | None) -> dict:
    """Merge stored section over the default so the response is always complete."""
    default = dict(DEFAULT_CONFIG.get(section, {}))
    stored = (doc or {}).get(section) if doc else None
    if isinstance(stored, dict):
        merged = {**default, **stored}
    else:
        merged = default
    for k in _SECTION_EXCLUDED_KEYS.get(section, ()):
        merged.pop(k, None)
    return merged


def _serialize_config(doc: dict | None) -> dict:
    """Return a JSON-safe view of every mutable section."""
    out: dict[str, Any] = {}
    for section in _MUTABLE_SECTIONS:
        out[section] = _serialize_section(section, _section_from_doc(section, doc))
    out["setup_complete"] = bool((doc or {}).get("setup_complete", False))
    return out


def _serialize_defaults() -> dict:
    out: dict[str, Any] = {}
    for section in _MUTABLE_SECTIONS:
        out[section] = _serialize_section(section, dict(DEFAULT_CONFIG.get(section, {})))
    return out


# ── Pydantic body ───────────────────────────────────────────────────────────


class SettingsPatch(BaseModel):
    roles: dict[str, Any] | None = None
    server: dict[str, Any] | None = None
    wyr: dict[str, Any] | None = None
    new_members: dict[str, Any] | None = None
    announcement: dict[str, Any] | None = None
    tag_tracker: dict[str, Any] | None = None
    drops: dict[str, Any] | None = None
    suggestions: dict[str, Any] | None = None
    boost: dict[str, Any] | None = None
    guide: dict[str, Any] | None = None


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/guilds/{guild_id}/settings")
async def get_settings(guild_id: str, session: dict = Depends(get_current_user)):
    role = await require_panel_access(session, guild_id)
    gid = int(guild_id)
    doc = await db.guild_config().find_one({"guild_id": gid})
    return {
        "config": _serialize_config(doc),
        "defaults": _serialize_defaults(),
        "panel_role": role,
        "mod_allowed_sections": sorted(MOD_ALLOWED_SECTIONS),
    }


@router.put("/guilds/{guild_id}/settings")
async def update_settings(
    guild_id: str,
    patch: SettingsPatch,
    session: dict = Depends(get_current_user),
):
    role = await require_panel_access(session, guild_id)
    gid = int(guild_id)
    doc = await db.guild_config().find_one({"guild_id": gid})

    payload = patch.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No section in patch")

    user_data = session.get("user_data") or {}
    actor_id = user_data.get("id") or session.get("user_id")
    actor_name = (
        user_data.get("global_name")
        or user_data.get("username")
        or str(actor_id or "unknown")
    )

    update_set: dict[str, Any] = {}
    audit_entries: list[dict] = []

    for section, value in payload.items():
        if section not in _MUTABLE_SECTIONS:
            raise HTTPException(status_code=400, detail=f"Section '{section}' is not editable")
        if role == "mod" and section not in MOD_ALLOWED_SECTIONS:
            raise HTTPException(
                status_code=403,
                detail=f"Mod role cannot edit '{section}'",
            )
        if not isinstance(value, dict):
            raise HTTPException(status_code=400, detail=f"Section '{section}' must be an object")

        allowed_keys = set(DEFAULT_CONFIG.get(section, {}).keys())
        allowed_keys -= _SECTION_EXCLUDED_KEYS.get(section, frozenset())
        for k in value:
            if k not in allowed_keys:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown field '{section}.{k}'",
                )

        _coerce_section_ids(section, value)

        # Surgical dotted $set of only the leaf keys that actually change, so a
        # concurrent edit to a different key in the same section isn't clobbered
        # by a whole-section overwrite.
        existing = (doc or {}).get(section)
        if not isinstance(existing, dict):
            existing = {}
        defaults = DEFAULT_CONFIG.get(section, {})
        for leaf_key, new_val in value.items():
            old_val = existing.get(leaf_key, defaults.get(leaf_key))
            if old_val != new_val:
                update_set[f"{section}.{leaf_key}"] = new_val
                audit_entries.append({
                    "section": section,
                    "key": f"{section}.{leaf_key}",
                    "old_value": old_val,
                    "new_value": new_val,
                    "action": "set",
                })

    if not update_set:
        # Nothing actually changed — return the current config unchanged.
        return {"config": _serialize_config(doc)}

    now = datetime.now(timezone.utc)
    update_set["updated_at"] = now
    update_ops: dict[str, Any] = {"$set": update_set}
    if doc is None:
        update_ops["$setOnInsert"] = {"guild_id": gid, "created_at": now}

    await db.guild_config().update_one(
        {"guild_id": gid},
        update_ops,
        upsert=True,
    )

    if audit_entries and actor_id is not None:
        try:
            audit_docs = [
                {
                    "guild_id": gid,
                    "actor_id": int(actor_id),
                    "actor_name": str(actor_name)[:128],
                    "source": "dashboard",
                    "section": e["section"],
                    "key": e["key"],
                    "old_value": e["old_value"],
                    "new_value": e["new_value"],
                    "action": e["action"],
                    "created_at": now,
                }
                for e in audit_entries
            ]
            await db.audit_log().insert_many(audit_docs)
        except Exception:
            logger.warning("Audit log write failed for guild %s", gid, exc_info=True)

    new_doc = await db.guild_config().find_one({"guild_id": gid})
    return {"config": _serialize_config(new_doc)}
