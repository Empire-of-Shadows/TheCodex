"""Member-scoped entitlements - what the logged-in user can actually use in a guild.

Owner rulings 2026-08-12 that define the semantics here (they must stay in step
with the bot's own enforcement in Features/ce_utilities/):

- Feature flags are GUILD-KEYED: a feature nobody configured is open to everyone;
  a feature granted to specific tiers is granted-members-only.
- Colours are strict: a member uses the colour sets assigned to their tiers or
  roles; a member with none posts with the server default colour. The one
  exception is ``embed.free_color_access`` (explicit admin opt-in), which frees
  the hex field for every member.
- The page shows ALL entitlements, with bot-granted items labeled as status.

Every section is independently nullable, matching the overview service: one slow
or broken collection cannot blank the page.
"""

import asyncio
from typing import Any

from dashboard._engine.auth.panel_access import member_role_ids
from dashboard._engine.discord_cache import discord_cache
from dashboard import db
from storage.log import get_logger

logger = get_logger("dashboard.services.entitlements")

#: The honest flag list - mirrors EMBED_FEATURES in the bot's embed_config_loader.
EMBED_FEATURES = ("basic_embed", "image_field", "footer_field", "timestamp")

FEATURE_LABELS = {
    "basic_embed": "Build embeds",
    "image_field": "Thumbnail image",
    "footer_field": "Footer text",
    "timestamp": "Timestamp",
}

#: Submission statuses still waiting on a moderator (wyr_submissions OPEN_STATUSES).
_SUBMISSION_OPEN = ("pending", "reviewing")


def _as_str_set(value: Any) -> set[str]:
    """A stored id/name list in whatever historical shape -> set of strings."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value if v is not None}
    return {str(value)}


def _member_tiers(embed_cfg: dict, roles: frozenset[str]) -> set[str]:
    """Tier names the member resolves to via embed.role_tier (role id -> tiers)."""
    role_tier = embed_cfg.get("role_tier") or {}
    tiers: set[str] = set()
    for role_id, tier_value in role_tier.items():
        if str(role_id) in roles:
            tiers |= _as_str_set(tier_value)
    return tiers


def _hex(value: Any) -> str | None:
    return f"#{value:06X}" if isinstance(value, int) else None


# -- Sections ----------------------------------------------------------------


async def _embed_section(
    guild_id: str, config: dict, roles: frozenset[str], is_admin: bool
) -> dict:
    embed_cfg = config.get("embed") or {}
    role_tier = embed_cfg.get("role_tier") or {}
    tiers = _member_tiers(embed_cfg, roles)

    # Command access mirrors has_embed_permissions: administrator OR an admin
    # role OR any tier role. The dashboard's "admin" tier covers the first two.
    access = is_admin or bool(tiers)
    enabled = embed_cfg.get("enabled")
    if enabled is None:
        enabled = bool(role_tier)

    # Guild-keyed feature gates: unconfigured = everyone, configured = granted
    # only. Mirrors the bot's describe_feature_access exactly: a feature granted
    # to a tier that NO role maps to resolves to no granting roles, so it stays
    # open rather than locking everyone out.
    feature_access = embed_cfg.get("feature_access") or {}
    features = []
    for key in EMBED_FEATURES:
        grants = _as_str_set(feature_access.get(key))
        granting_roles = {
            str(role_id)
            for role_id, tier_value in role_tier.items()
            if _as_str_set(tier_value) & grants
        }
        restricted = bool(granting_roles)
        features.append({
            "key": key,
            "label": FEATURE_LABELS[key],
            "available": (not restricted) or bool(tiers & grants),
            "restricted": restricted,
        })

    # Colours: strict unless the guild opted into free access.
    free_access = bool(embed_cfg.get("free_color_access"))
    sets = await _member_color_sets(guild_id, roles, tiers)
    mode = "free" if free_access else ("palette" if sets else "default_only")

    description_limits = embed_cfg.get("description_limits") or {}
    tier_limits = description_limits.get("tier_limits") or {}
    applicable = [
        v for t, v in tier_limits.items() if t in tiers and isinstance(v, int)
    ]
    default_limit = description_limits.get("default_limit")
    if not isinstance(default_limit, int):
        default_limit = 500
    limit = min(max(applicable) if applicable else default_limit, 4000)

    return {
        "access": access,
        "enabled": bool(enabled),
        "tiers": sorted(tiers),
        "features": features,
        "colors": {
            "mode": mode,
            "default_color": _hex(embed_cfg.get("default_color")),
            "sets": sets,
        },
        "description_limit": limit,
    }


async def _member_color_sets(
    guild_id: str, roles: frozenset[str], tiers: set[str]
) -> list[dict]:
    """The colour sets assigned to this member, grouped for display."""
    assignment_cursor = db.color_set_assignments().find({"guild_id": str(guild_id)})
    my_set_ids: set[str] = set()
    async for assignment in assignment_cursor:
        target_type = assignment.get("target_type")
        target_id = str(assignment.get("target_id"))
        if (target_type == "tier" and target_id in tiers) or (
            target_type == "role" and target_id in roles
        ):
            my_set_ids.add(str(assignment.get("color_set_id")))

    if not my_set_ids:
        return []

    # Sets per guild are few (8 seeded); fetch them all and join by stringified
    # _id so an ObjectId-vs-string mismatch in the stored reference cannot drop one.
    sets = []
    async for doc in db.color_sets().find({"guild_id": str(guild_id)}):
        if str(doc.get("_id")) not in my_set_ids:
            continue
        colors = {}
        for color in doc.get("colors") or []:
            name = color.get("name")
            value = _hex(color.get("value"))
            if name and value:
                colors[str(name)] = value
        sets.append({"name": doc.get("name") or "Unnamed set", "colors": colors})
    return sets


async def _capabilities_section(
    config: dict, roles: frozenset[str], is_admin: bool
) -> list[dict]:
    wyr_cfg = config.get("wyr") or {}
    drops_cfg = config.get("drops") or {}

    reviewer_role = wyr_cfg.get("submission_moderator_role_id")
    manager_role = drops_cfg.get("manager_role_id")

    return [
        {
            "key": "panel_access",
            "label": "Admin panel and settings",
            "granted": is_admin,
        },
        {
            "key": "wyr_reviewer",
            "label": "Review suggested questions",
            "granted": is_admin
            or bool(reviewer_role and str(reviewer_role) in roles),
        },
        {
            "key": "drops_manager",
            "label": "Manage free game drops",
            "granted": is_admin or bool(manager_role and str(manager_role) in roles),
        },
    ]


def _walk_role_actions(node: Any, found: set[str]) -> None:
    """Collect every {"action": "role", "target": <id>} in a component tree."""
    if isinstance(node, dict):
        if node.get("action") == "role" and node.get("target"):
            found.add(str(node["target"]))
        for value in node.values():
            _walk_role_actions(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk_role_actions(item, found)


async def _self_serve_section(
    guild_id: str, config: dict, roles: frozenset[str]
) -> dict:
    wyr_cfg = config.get("wyr") or {}
    ping_role = wyr_cfg.get("ping_role_id")

    # Self-assignable roles authored into the board and the guide.
    board_targets: set[str] = set()
    guide_targets: set[str] = set()
    # Walk the whole stored document - the component tree's field name has
    # varied across store versions, and the action shape is unmistakable.
    board_doc = await db.board_content().find_one({"guild_id": str(guild_id)})
    if board_doc:
        board_doc.pop("_id", None)
        _walk_role_actions(board_doc, board_targets)
    guide_doc = await db.guide_content().find_one({"guild_id": str(guild_id)})
    if guide_doc:
        guide_doc.pop("_id", None)
        _walk_role_actions(guide_doc, guide_targets)

    # Best-effort role names via the engine cache; ids alone still render.
    names: dict[str, str] = {}
    try:
        for role in await discord_cache.guild_roles(str(guild_id)):
            names[str(role.get("id"))] = role.get("name") or ""
    except Exception as e:  # noqa: BLE001 - names are cosmetic
        logger.debug("Role-name lookup failed for guild %s: %s", guild_id, e)

    toggle_roles = [
        {
            "source": source,
            "role_id": target,
            "name": names.get(target) or None,
            "held": target in roles,
        }
        for source, targets in (("board", board_targets), ("guide", guide_targets))
        for target in sorted(targets)
    ]

    return {
        "wyr_ping": {
            "available": bool(ping_role) and bool(wyr_cfg.get("enabled")),
            "subscribed": bool(ping_role and str(ping_role) in roles),
        },
        "toggle_roles": toggle_roles,
    }


async def _status_section(
    guild_id: str, user_id: str, config: dict, roles: frozenset[str]
) -> dict:
    nm_cfg = config.get("new_members") or {}
    whitelist_role = nm_cfg.get("whitelist_role_id")
    entry = await db.serverdata_whitelist().find_one({
        "guild_id": str(guild_id),
        "user_id": str(user_id),
        "is_active": True,
    })
    return {
        "screening_whitelisted": entry is not None,
        "whitelist_role_held": bool(whitelist_role and str(whitelist_role) in roles),
    }


async def _submissions_section(guild_id: str, user_id: str, config: dict) -> dict:
    wyr_cfg = config.get("wyr") or {}
    enabled = bool(wyr_cfg.get("submissions_enabled")) and bool(
        wyr_cfg.get("submission_review_channel_id")
        or wyr_cfg.get("submission_moderator_role_id")
    )
    pending = await db.daily_wyr_submissions().count_documents({
        "guild_id": str(guild_id),
        "user_id": str(user_id),
        "status": {"$in": list(_SUBMISSION_OPEN)},
    })
    max_pending = wyr_cfg.get("submission_max_pending")
    if not isinstance(max_pending, int):
        max_pending = 3
    return {"enabled": enabled, "pending": pending, "max": max_pending}


# -- Entry point --------------------------------------------------------------


async def _safe(coro):
    """A failed section returns None instead of failing the whole payload."""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001 - deliberate section isolation
        logger.error("Entitlements section failed: %s", e, exc_info=True)
        return None


async def get_entitlements(
    guild_id: str, user_id: str, is_admin: bool
) -> dict:
    """Everything the member can use in this guild, plus their status there."""
    config = await db.guild_config().find_one({"guild_id": str(guild_id)}) or {}
    roles = await member_role_ids(str(guild_id), str(user_id))

    embed, capabilities, self_serve, status, submissions = await asyncio.gather(
        _safe(_embed_section(guild_id, config, roles, is_admin)),
        _safe(_capabilities_section(config, roles, is_admin)),
        _safe(_self_serve_section(guild_id, config, roles)),
        _safe(_status_section(guild_id, user_id, config, roles)),
        _safe(_submissions_section(guild_id, user_id, config)),
    )

    return {
        "guild_id": str(guild_id),
        "embed": embed,
        "capabilities": capabilities,
        "self_serve": self_serve,
        "status": status,
        "submissions": submissions,
    }
