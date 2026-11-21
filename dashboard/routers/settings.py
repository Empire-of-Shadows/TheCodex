"""Per-guild settings GET/PUT - reads + writes Settings.GuildConfig.

Mirrors the panel groups defined in admin/settings/panel_configs.py but
exposes them through a single section-keyed JSON endpoint suitable for
the web dashboard. The dashboard is admin-only - there is no mod tier -
so a caller who reaches these routes may edit every mutable section.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

import pytz
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dashboard import db
from dashboard._engine.discord_cache import (
    PERMISSION_BITS,
    dangerous_role_permissions,
    discord_cache,
    missing_permissions,
    permission_label,
)
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import require_panel_access
from storage.log import get_logger

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from storage.settings.config_manager import DEFAULT_CONFIG  # noqa: E402
from Features.announcements.thread_name import thread_name_format_error  # noqa: E402

logger = get_logger("dashboard.routers.settings")

router = APIRouter(tags=["settings"])

# Sections the dashboard may mutate. greeting_components is intentionally
# excluded - the builder route owns that field. embed is also excluded
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

# Subkeys that exist inside a section's stored doc but are NOT managed by
# the settings dashboard. Stripped from GET responses (so the frontend draft
# does not include them) and excluded from PUT allowed-keys (so an honest
# client can never reintroduce them).
_SECTION_EXCLUDED_KEYS: dict[str, frozenset[str]] = {
    # greeting_components is owned by the builder route.
    "new_members": frozenset({"greeting_components"}),
    # tiers is a dead pre-v2-collapse field that nothing reads or writes. Kept in the
    # exclusion list only so a stored doc that still carries it (until migration m12
    # `$unset`s it) cannot be echoed back and re-saved by the dashboard. The comment that
    # used to be here claimed the Discord panel managed it - it never did. The live
    # role-to-tier mapping is `embed.role_tier` (Embed Settings -> Role Tier Mapping),
    # and `embed` is excluded from this form wholesale.
    #
    # mod_role_ids is the retired moderator tier (removed 2026-08-06; admin surfaces
    # are admin-only fleet-wide). Listed here for the same reason as tiers: a stored
    # doc still carrying it until migration m13 `$unset`s it must not be echoed into
    # the client draft, because PUT would then reject the whole roles section as an
    # unknown field and Panel Access Roles could not be saved.
    "roles": frozenset({"tiers", "mod_role_ids"}),
}

# ── ID coercion ─────────────────────────────────────────────────────────────
#
# Discord snowflakes exceed JS Number safe range. Stringify on the way out,
# coerce back to int on the way in.

_CHANNEL_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "server": ("admin_channel_id",),
    "wyr": ("channel_id", "submission_review_channel_id"),
    "new_members": ("greeting_channel_id",),
    "announcement": ("channel_id",),
    "drops": ("channel_id",),
    "suggestions": ("channel_id",),
    "boost": ("channel_id",),
    "guide": ("channel_id",),
}

_ROLE_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "wyr": ("ping_role_id", "submission_moderator_role_id"),
    "new_members": ("whitelist_role_id",),
    "drops": ("manager_role_id",),
    "tag_tracker": ("role_id",),
}

_ROLE_ID_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "roles": ("admin_role_ids",),
}


# ── Required fields ─────────────────────────────────────────────────────────
#
# A feature that is switched on but missing the channel (or role, or tag) it
# cannot run without saves fine and then silently does nothing. Each rule below
# was checked against the code that runs the feature (2026-11-20):
#
#   wyr.channel_id              Features/daily/WYR.py posts nowhere without it
#   wyr review channel OR role  WYR.py:254 refuses suggestions when BOTH are unset;
#                               either one is enough
#   new_members greeting        joining.py:574 skips the greeting without a channel
#   new_members starter role    joining.py:455 needs a role or a name to create one
#   drops.channel_id            prime-drops.py:162 posts nothing without it
#
# Announcements deliberately have NO rule: they have no on/off switch, and
# thread_auto_create defaults to True with no channel, which is the feature's
# normal "off" state (announcements.py:41 returns early). A rule there would
# turn every untouched server's Announcements page red (review 2026-11-20).
#   boost.channel_id            boost_tracker.py:355 logs nothing without it
#   tag_tracker tag AND role    tag_tracker.py:53 is inactive without both
#
# The settings page shows the same messages in red and keeps Save switched off
# (components/settings/requirements.ts, which must say the same thing). This
# copy is the one that holds when a request does not come from that page.

def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _requirement_errors(section: str, s: dict) -> list[str]:
    """What a switched-on feature in ``s`` (the section as it would be saved) is missing."""
    errors: list[str] = []
    if section == "wyr":
        if s.get("enabled") and _blank(s.get("channel_id")):
            errors.append("Pick a WYR channel, or switch Would You Rather off.")
        if (
            s.get("submissions_enabled")
            and _blank(s.get("submission_review_channel_id"))
            and _blank(s.get("submission_moderator_role_id"))
        ):
            errors.append(
                "Pick a suggestion review channel or a reviewer role, or switch member suggestions off."
            )
    elif section == "new_members":
        if s.get("enabled") and s.get("greeting_enabled") and _blank(s.get("greeting_channel_id")):
            errors.append("Pick a greeting channel, or switch greeting messages off.")
        if (
            s.get("enabled")
            and s.get("whitelist_enabled")
            and _blank(s.get("whitelist_role_id"))
            and _blank(s.get("whitelist_role_name"))
        ):
            errors.append(
                "Pick a whitelist role or type a name for one, or switch the whitelist system off."
            )
    elif section == "drops":
        if s.get("enabled") and _blank(s.get("channel_id")):
            errors.append("Pick a drops channel, or switch drops off.")
    elif section == "boost":
        if s.get("enabled") and _blank(s.get("channel_id")):
            errors.append("Pick a boost log channel, or switch the Boost Tracker off.")
    elif section == "tag_tracker":
        if s.get("enabled") and _blank(s.get("server_tag")):
            errors.append("Type your server tag, or switch the Tag Tracker off.")
        if s.get("enabled") and _blank(s.get("role_id")):
            errors.append("Pick a tag role, or switch the Tag Tracker off.")
    return errors


# ── What the bot needs in a picked channel or role ─────────────────────────
#
# The panel refuses a channel the bot cannot use and a role it cannot hand out;
# the dashboard used to save both, and the feature then failed silently (found
# 2026-11-20). The lists are the panel's own, copied here because the dashboard
# process does not import the admin package; a test compares them with the panel
# constants (panel_configs, wyr_question_nodes, drops_nodes, tracker_nodes) so
# they cannot drift. Only a CHANGED value is checked, and a Discord lookup that
# fails lets the save through, like every other dashboard's check.

_CHANNEL_PERMS: dict[tuple[str, str], list[str]] = {
    ("wyr", "channel_id"): [
        "view_channel", "send_messages", "embed_links",
        "create_public_threads", "send_messages_in_threads",
    ],
    ("wyr", "submission_review_channel_id"): ["view_channel", "send_messages", "embed_links"],
    ("new_members", "greeting_channel_id"): ["view_channel", "send_messages"],
    ("announcement", "channel_id"): [
        "view_channel", "read_message_history", "create_public_threads",
        "send_messages_in_threads", "embed_links",
    ],
    ("suggestions", "channel_id"): [
        "view_channel", "send_messages", "embed_links",
        "create_public_threads", "send_messages_in_threads",
    ],
    ("drops", "channel_id"): ["view_channel", "send_messages", "embed_links"],
    ("boost", "channel_id"): ["view_channel", "send_messages"],
}
_TRACKER_CHANNEL_PERMS = ["view_channel"]

_CHANNEL_LABELS: dict[tuple[str, str], str] = {
    ("wyr", "channel_id"): "WYR channel",
    ("wyr", "submission_review_channel_id"): "suggestion review channel",
    ("new_members", "greeting_channel_id"): "greeting channel",
    ("announcement", "channel_id"): "announcement channel",
    ("suggestions", "channel_id"): "suggestion channel",
    ("drops", "channel_id"): "drops channel",
    ("boost", "channel_id"): "boost log channel",
}

# Roles the bot hands out itself, so it must be able to assign them (the panel's
# requires_role_manage nodes: WYR ping role, whitelist role, tag role).
_ASSIGNED_ROLES: dict[tuple[str, str], str] = {
    ("wyr", "ping_role_id"): "ping role",
    ("new_members", "whitelist_role_id"): "whitelist role",
    ("tag_tracker", "role_id"): "tag role",
}


# Sections whose `timezone` the bot schedules with (the dashboard's region/zone picker).
_TIMEZONE_SECTIONS = frozenset({"wyr", "drops"})


def _id_changed(new: Any, old: Any) -> bool:
    return new not in (None, "") and str(new) != str(old or "")


async def _channel_problem(gid: str, channel_id: Any, perms_needed: list[str], label: str) -> str | None:
    perms = await discord_cache.bot_channel_permissions(gid, str(channel_id))
    missing = missing_permissions(perms, perms_needed)
    if not missing:
        return None
    return (
        f"TheCodex is missing permissions in that {label}: "
        f"{', '.join(permission_label(m) for m in missing)}. Grant them in the "
        f"channel's settings, or pick another channel."
    )


def _dangerous_role_text(name: str, found: list[str]) -> str:
    """The refusal for a role the bot would hand out that carries moderator powers
    (owner ruling 2026-11-20; same words as the panel's dangerous_role_message)."""
    return (
        f"@{name} has {', '.join(found)}, so TheCodex will not hand it out: members "
        f"would get those powers without an admin choosing them. Pick a role without "
        f"them, or remove them from the role in Server Settings > Roles."
    )


async def _role_problem(gid: str, role_id: Any, label: str) -> str | None:
    roles = await discord_cache.guild_roles_raw(gid)
    bot_roles = await discord_cache.bot_member_role_ids(gid)
    perms = await discord_cache.bot_guild_permissions(gid)
    if not roles or bot_roles is None or perms is None:
        return None  # could not check - let it through
    role = next((r for r in roles if str(r["id"]) == str(role_id)), None)
    if role is None:
        return f"That {label} is not in this server any more. Pick another role."
    if str(role["id"]) == gid:
        return f"@everyone cannot be the {label}. Pick a normal role."
    if role.get("managed"):
        return (
            f"@{role['name']} is managed by an integration, so Discord does not let "
            f"anyone hand it out. Pick a normal role for the {label}."
        )
    dangerous = dangerous_role_permissions(role.get("permissions"))
    if dangerous:
        return _dangerous_role_text(role["name"], dangerous)
    if not perms & PERMISSION_BITS["manage_roles"]:
        return (
            f"TheCodex needs the Manage Roles permission to hand out the {label}. "
            f"Grant it in Server Settings > Roles."
        )
    top = max(
        (int(r.get("position", 0)) for r in roles if str(r["id"]) in {str(b) for b in bot_roles}),
        default=0,
    )
    if int(role.get("position", 0)) >= top:
        return (
            f"TheCodex's highest role must be above @{role['name']} to hand it out. "
            f"Move the bot's role up in Server Settings > Roles, or pick a lower role."
        )
    return None


async def _discord_problems(gid: str, section: str, value: dict, existing: dict) -> list[str]:
    """What the bot cannot do with the channels and roles this save changes."""
    problems: list[str] = []
    for (sec, key), needed in _CHANNEL_PERMS.items():
        if sec == section and key in value and _id_changed(value[key], existing.get(key)):
            p = await _channel_problem(gid, value[key], needed, _CHANNEL_LABELS[(sec, key)])
            if p:
                problems.append(p)
    if section == "drops" and isinstance(value.get("tracker_channels"), dict):
        old = existing.get("tracker_channels") or {}
        for bucket, cid in value["tracker_channels"].items():
            if _id_changed(cid, old.get(bucket)):
                p = await _channel_problem(gid, cid, _TRACKER_CHANNEL_PERMS, f"{bucket} tracker channel")
                if p:
                    problems.append(p)
    for (sec, key), label in _ASSIGNED_ROLES.items():
        if sec == section and key in value and _id_changed(value[key], existing.get(key)):
            p = await _role_problem(gid, value[key], label)
            if p:
                problems.append(p)
    return problems


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
            # The permission role list persists as STRINGS (migration m9), unlike the
            # scalar channel/role fields above which the config still stores as ints.
            value[k] = [str(v) for v in value[k] if v is not None]
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
    gid = str(int(guild_id))
    doc = await db.guild_config().find_one({"guild_id": gid})
    return {
        "config": _serialize_config(doc),
        "defaults": _serialize_defaults(),
        "panel_role": role,
    }


@router.put("/guilds/{guild_id}/settings")
async def update_settings(
    guild_id: str,
    patch: SettingsPatch,
    session: dict = Depends(get_current_user),
):
    await require_panel_access(session, guild_id)
    # Both the config and the audit log are string-keyed (migrations m4 / m8).
    gid = str(int(guild_id))
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

        if section == "announcement" and "thread_name_format" in value:
            format_error = thread_name_format_error(value["thread_name_format"])
            if format_error:
                raise HTTPException(status_code=400, detail=format_error)

        existing = (doc or {}).get(section)
        if not isinstance(existing, dict):
            existing = {}
        defaults = DEFAULT_CONFIG.get(section, {})

        # Judge the section as it would stand after this save, so a patch that
        # carries only some keys is checked against what is already stored.
        missing = _requirement_errors(section, {**defaults, **existing, **value})
        if missing:
            raise HTTPException(status_code=400, detail=" ".join(missing))

        # WYR.py:800 and prime-drops.py:207 hand this straight to pytz; an unknown
        # name stops that guild's daily post (WYR raises, drops skips). Checked
        # on change only, so a stored older name never blocks an unrelated save.
        if (
            section in _TIMEZONE_SECTIONS
            and "timezone" in value
            and value["timezone"] != existing.get("timezone", defaults.get("timezone"))
            and value["timezone"] not in pytz.all_timezones_set
        ):
            raise HTTPException(
                status_code=400,
                detail="That timezone is not one TheCodex knows. Pick a region and a zone from the lists.",
            )

        problems = await _discord_problems(gid, section, value, existing)
        if problems:
            raise HTTPException(status_code=400, detail=" ".join(problems))

        # Surgical dotted $set of only the leaf keys that actually change, so a
        # concurrent edit to a different key in the same section isn't clobbered
        # by a whole-section overwrite.
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
        # Nothing actually changed - return the current config unchanged.
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
                    "actor_id": str(actor_id),
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
