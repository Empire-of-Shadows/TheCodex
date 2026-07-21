"""TheCodex - admin engine bindings (the per-bot seam).

The vendored engine (``admin_cog.py``) is byte-identical across every bot; it reaches all of
TheCodex's backends through the names defined here. See ``admin_engine/bindings_reference.py``
for the full contract.

Persistence flows through TheCodex's own managers (which write via the shared db_manager's
collection managers): structured per-guild config + flat settings through ``GuildConfigManager``
and audit entries through the engine ``AuditLog`` service. The panel binds its leaves to bot-specific
action classes (``EmbedConfigActions``, ``GuideActions``, …) that use the config manager
directly, so the generic ``config_*`` doers here back the flat settings store and the ``db_*``
doers are inert (the panel has no engine collection actions - same pattern as TheHost).

TheCodex has no guild-entitlement premium system, so ``is_premium`` is always ``False``.
"""

from __future__ import annotations

from typing import Any

import discord

from storage.settings.config_manager import (
    _STRUCTURED_KEYS,
    GuildConfig,
    get_config,
    get_config_manager,
)
from storage.services import AuditLog
from .setup_gatekeeper import setup_gatekeeper

import logging

# Re-export the static branding text the engine reads by name.
from .panel_branding import OVERVIEW_FOOTER, SETUP_GUIDE_TEXT
# Reuse the engine's shared tier resolver instead of a hand-rolled per-bot copy.
from ..auth import resolve_panel_role_from_config

logger = logging.getLogger("AdminBindings")


# ── Static configuration ────────────────────────────────────────────────────────

BOT_NAME = "The Codex"

# Mod-tier access is declared per-node via ``PanelNode.mod_allowed`` flags in panel_configs
# (the engine's ``auth.effective_mod_allowed`` reads them); this legacy top-level-category
# fallback is intentionally empty. No section grants blanket mod access by category.
MOD_ALLOWED_CATEGORIES: set[str] = set()

# OVERVIEW_FOOTER / SETUP_GUIDE_TEXT are re-exported from panel_branding above.


# ── Tier resolution ──────────────────────────────────────────────────────────────

async def resolve_panel_role(user: discord.Member, guild_id: int) -> str:
    """Return "admin" | "mod" | "none".

    Delegates to the shared engine resolver (``auth.resolve_panel_role_from_config``), which
    reads the admin/mod role-id lists from config via ``config_get`` at the canonical paths
    ``roles.admin_role_ids`` / ``roles.mod_role_ids`` (Manage Server always resolves to
    "admin"). Those are structured ``GuildConfig`` fields; ``config_get`` below routes them to
    the typed store, so the engine reads the very lists the role-picker writes."""
    return await resolve_panel_role_from_config(user, int(guild_id))


# ── Dashboard flags (setup-guide toggle, etc.) ───────────────────────────────────

async def get_setting(key: str, guild_id: int, default: Any = None):
    cm = await get_config_manager()
    return await cm.get_setting(key, int(guild_id), default=default)


async def set_setting(key: str, value: Any, guild_id: int) -> None:
    cm = await get_config_manager()
    await cm.set_setting(key, value, int(guild_id))


# ── Premium ──────────────────────────────────────────────────────────────────────

async def is_premium(guild_id: int) -> bool:
    return False  # TheCodex has no guild-entitlement premium tier.


# ── Cache invalidation ───────────────────────────────────────────────────────────

def invalidate_caches(guild_id: int) -> None:
    """Invalidate the setup gatekeeper's per-guild cache after a settings mutation."""
    try:
        setup_gatekeeper.invalidate(int(guild_id))
    except Exception as e:  # best-effort: never block a save
        logger.debug(f"invalidate_caches skipped for {guild_id}: {e}")


# ── Audit log ────────────────────────────────────────────────────────────────────

_audit_log: "AuditLog | None" = None


def _get_audit_log() -> AuditLog:
    """The engine ``AuditLog`` over the ``settings_audit_log`` collection, replacing the
    hand-rolled ``AuditLogger``. Uses the generic ``.log()`` (not ``log_config_change``,
    which stringifies ``guild_id``) so the persisted int ``guild_id`` / ``actor_id`` shape
    is unchanged; ID normalization is the scheduled int->str migration's job."""
    global _audit_log
    if _audit_log is None:
        from storage.settings.collections import db_manager
        _audit_log = AuditLog(db_manager.get_collection_manager("settings_audit_log"))
    return _audit_log


async def audit_log_entry(
    *,
    guild_id: int,
    actor_id: int,
    actor_name: str,
    section: str,
    key: str,
    old_value: object,
    new_value: object,
    action: str,
) -> None:
    await _get_audit_log().log(
        guild_id=int(guild_id),
        actor_id=int(actor_id),
        actor_name=str(actor_name)[:128],
        source="discord",
        section=section,
        key=key,
        old_value=old_value,
        new_value=new_value,
        action=action,
    )


# ── Config access (dotted-path, backend-agnostic) ────────────────────────────────
# TheCodex keeps one document per guild split in two: structured top-level keys (the typed
# ``GuildConfig`` - ``roles``, ``wyr``, …) reached via ``get_config`` / ``save_config``, and
# flat "legacy/misc" keys reached via ``get_setting`` / ``set_setting``. The engine's config
# contract is a single dotted-path getter/setter, so these doers route a path to the right
# half by its head key: ``roles.admin_role_ids`` -> the typed store, ``hide_setup_guide`` ->
# the flat store. This seam adapter is what lets the shared resolver read ``roles.*`` (see
# ``resolve_panel_role`` above). Codex's structured writes normally flow through bot-specific
# action classes; the structured branch of ``config_set`` / ``config_unset`` exists so the
# generic engine doers honor the same contract.


def _dig(section, dotted: str, default):
    """Read a nested value from a structured section by a dotted sub-path."""
    cur = section
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def _bury(section: dict, dotted: str, value) -> None:
    """Write ``value`` into a structured section at a dotted sub-path, creating dicts."""
    parts = dotted.split(".")
    cur = section
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


async def config_get(guild_id: int, path: str, default=None):
    head, _, rest = path.partition(".")
    if head in _STRUCTURED_KEYS:
        cfg = await get_config(int(guild_id))
        section = getattr(cfg, head, None)
        if not rest:
            return section if section is not None else default
        return _dig(section, rest, default)
    cm = await get_config_manager()
    return await cm.get_setting(path, int(guild_id), default=default)


async def config_set(guild_id: int, path: str, value) -> bool:
    head, _, rest = path.partition(".")
    if head in _STRUCTURED_KEYS:
        cm = await get_config_manager()
        cfg = await cm.get_config(int(guild_id))
        if not rest:
            setattr(cfg, head, value)
        else:
            section = getattr(cfg, head, None)
            if not isinstance(section, dict):
                return False
            _bury(section, rest, value)
        return await cm.save_config(cfg)
    cm = await get_config_manager()
    return await cm.set_setting(path, value, int(guild_id))


async def config_unset(guild_id: int, path: str) -> bool:
    head, _, rest = path.partition(".")
    if head in _STRUCTURED_KEYS:
        cm = await get_config_manager()
        cfg = await cm.get_config(int(guild_id))
        if not rest:
            # Unset a whole structured section -> reset it to its declared default,
            # rather than silently doing nothing and returning success.
            default_cfg = GuildConfig(guild_id=int(guild_id))
            setattr(cfg, head, getattr(default_cfg, head))
        else:
            section = getattr(cfg, head, None)
            if isinstance(section, dict):
                parts = rest.split(".")
                cur = section
                for part in parts[:-1]:
                    cur = cur.get(part) if isinstance(cur, dict) else None
                    if not isinstance(cur, dict):
                        return True  # nothing to unset - treat as done
                cur.pop(parts[-1], None)
        return await cm.save_config(cfg)
    cm = await get_config_manager()
    # $unset (not a null write) so the key reads back as its default.
    return await cm.unset_setting(path, int(guild_id))


# ── Collection access (inert - TheCodex's panel has no engine collection actions) ─

async def db_find(collection: str, query: dict, *, sort=None, limit: int | None = None) -> list[dict]:
    return []


async def db_count(collection: str, query: dict) -> int:
    return 0


async def db_delete_one(collection: str, query: dict) -> bool:
    return False


async def db_delete_many(collection: str, query: dict) -> int:
    return 0


async def db_update_one(collection: str, query: dict, update: dict, *, upsert: bool = False) -> bool:
    return False


async def db_insert_one(collection: str, doc: dict):
    return None
