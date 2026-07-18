"""TheCodex — admin engine bindings (the per-bot seam).

The vendored engine (``admin_cog.py``) is byte-identical across every bot; it reaches all of
TheCodex's backends through the names defined here. See ``admin_engine/bindings_reference.py``
for the full contract.

Persistence flows through TheCodex's own managers (which write via the shared db_manager's
collection managers): structured per-guild config + flat settings through ``GuildConfigManager``
and audit entries through ``storage/audit_log.py``. The panel binds its leaves to bot-specific
action classes (``EmbedConfigActions``, ``GuideActions``, …) that use the config manager
directly, so the generic ``config_*`` doers here back the flat settings store and the ``db_*``
doers are inert (the panel has no engine collection actions — same pattern as TheHost).

TheCodex has no guild-entitlement premium system, so ``is_premium`` is always ``False``.
"""

from __future__ import annotations

from typing import Any

import discord

from storage.settings.config_manager import get_config, get_config_manager
from storage.audit_log import get_audit_logger
from storage.setup_gatekeeper import setup_gatekeeper

import logging

# Re-export the static branding text the engine reads by name.
from .panel_branding import OVERVIEW_FOOTER, SETUP_GUIDE_TEXT
from . import role_auth

logger = logging.getLogger("AdminBindings")


# ── Static configuration ────────────────────────────────────────────────────────

BOT_NAME = "The Codex"

# Mod-tier sections come from the declarative ``mod_allowed`` flags on panel nodes; the
# legacy category set falls back to role_auth's (empty) section set.
MOD_ALLOWED_CATEGORIES: set[str] = set(role_auth.MOD_ALLOWED_SECTIONS)

# OVERVIEW_FOOTER / SETUP_GUIDE_TEXT are re-exported from panel_branding above.


# ── Tier resolution ──────────────────────────────────────────────────────────────

async def resolve_panel_role(user: discord.Member, guild_id: int) -> str:
    """Return "admin" | "mod" | "none" using TheCodex's role logic (Manage Server, then the
    canonical ``GuildConfig.roles`` admin/mod id lists)."""
    cfg = await get_config(int(guild_id))
    return role_auth.get_panel_role(user, cfg)


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
    al = await get_audit_logger()
    await al.log(
        guild_id=int(guild_id),
        actor_id=int(actor_id),
        actor_name=actor_name,
        source="discord",
        section=section,
        key=key,
        old_value=old_value,
        new_value=new_value,
        action=action,
    )


# ── Config access (over the flat per-guild settings store) ───────────────────────
# TheCodex's panel leaves use the config manager via bot-specific action classes; these
# generic doers back the flat settings collection for engine-contract completeness.

async def config_get(guild_id: int, path: str, default=None):
    cm = await get_config_manager()
    return await cm.get_setting(path, int(guild_id), default=default)


async def config_set(guild_id: int, path: str, value) -> bool:
    cm = await get_config_manager()
    return await cm.set_setting(path, value, int(guild_id))


async def config_unset(guild_id: int, path: str) -> bool:
    cm = await get_config_manager()
    return await cm.set_setting(path, None, int(guild_id))


# ── Collection access (inert — TheCodex's panel has no engine collection actions) ─

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
