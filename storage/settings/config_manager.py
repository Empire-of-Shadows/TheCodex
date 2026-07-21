"""
Unified Guild Configuration Manager for TheCodex Bot

Feature-centric schema: each feature owns its channel ID, role ID, and
settings in one place.  Cross-feature identifiers (admin/moderator roles,
server admin channel) remain at the top level.

Structured fields are managed through GuildConfig / save_config().
Flat settings (legacy or miscellaneous) can still be written through
get_setting() / set_setting() for any remaining callers, but all WYR
and embed settings are now fully absorbed into the structured config.
"""

import asyncio
import copy
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from storage.log import get_logger

logger = get_logger("GuildConfig")


def _config_update_ops(old: Dict[str, Any], new: Dict[str, Any],
                       prefix: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Diff two config dicts into surgical MongoDB ``$set`` / ``$unset`` operations.

    Returns ``(sets, unsets)`` keyed by dotted path. Nested dicts recurse so only the
    leaves that actually changed are written; lists and scalars are treated as atomic.
    This lets a bot-side save touch ONLY the fields this caller changed, so it can no
    longer revert an unrelated concurrent dashboard edit back to a stale value.
    """
    sets: Dict[str, Any] = {}
    unsets: Dict[str, Any] = {}
    for key, new_val in new.items():
        path = f"{prefix}{key}"
        if key not in old:
            sets[path] = new_val
            continue
        old_val = old[key]
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            sub_sets, sub_unsets = _config_update_ops(old_val, new_val, path + ".")
            sets.update(sub_sets)
            unsets.update(sub_unsets)
        elif old_val != new_val:
            sets[path] = new_val
    for key in old:
        if key not in new:
            unsets[f"{prefix}{key}"] = ""
    return sets, unsets

# ─────────────────────────────────────────────────────────────────────────────
# Per-guild flat setting defaults  (kept minimal — most settings are structured)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SETTINGS: Dict[str, Any] = {}

# Keys that belong to the structured GuildConfig portion of the document.
# Flat settings are any top-level key NOT in this set.
_STRUCTURED_KEYS: frozenset = frozenset({
    "_id", "guild_id",
    "roles", "server",
    "wyr", "new_members", "announcement", "tag_tracker",
    "drops", "suggestions", "boost", "embed", "guide",
    "setup_complete", "color_tiers_seeded",
    "created_at", "updated_at",
})

# ─────────────────────────────────────────────────────────────────────────────
# Default factory functions
# ─────────────────────────────────────────────────────────────────────────────

def _default_roles() -> Dict[str, Any]:
    return {
        "admin_role_ids": [],
        "mod_role_ids": [],
        "tiers": {},
    }


def _default_server() -> Dict[str, Any]:
    return {
        "admin_channel_id": None,
    }


def _default_wyr() -> Dict[str, Any]:
    return {
        "enabled": False,
        "channel_id": None,
        "ping_role_id": None,
        "post_hour": 6,
        "post_minute": 0,
        "timezone": "America/Chicago",
        "default_category": "sfw",
        "thread_name_format": "🎲 WYR · Q{question_num} · {date}",
        "thread_starter_message": (
            "🎲 **{question}**\n\n"
            "1️⃣ {option_1}\n"
            "2️⃣ {option_2}\n\n"
            "What's your reasoning? Share your thoughts below!"
        ),
        "thread_auto_archive": 1440,
        "mapping_cleanup_days": 30,
        "skip_initial_post": False,
    }


def _default_new_members() -> Dict[str, Any]:
    return {
        "enabled": False,
        "account_age_requirement_days": 90,
        "auto_kick": True,
        "welcome_channel_id": None,
        "whitelist_role_id": None,
        "whitelist_enabled": True,
        "whitelist_role_name": "Whitelisted New Member",
        "welcome_message_enabled": True,
        "welcome_components": None,
    }


def _default_announcement() -> Dict[str, Any]:
    return {
        "channel_id": None,
        "thread_auto_create": True,
        "thread_name_format": "💬 {message_content}",
        "thread_auto_archive_duration": 1440,
        "thread_welcome_message": "💬 **Discussion Thread**\n\nDiscuss this announcement here!",
        "auto_delete_threads": True,
    }


def _default_tag_tracker() -> Dict[str, Any]:
    return {
        "enabled": False,
        "server_tag": None,
        "role_id": None,
    }


def _default_drops() -> Dict[str, Any]:
    return {
        "enabled": False,
        "channel_id": None,
        "tracker_channels": {"Updates": None, "Free": None, "Prime": None},
        "manager_role_id": None,
        "post_hour": 6,
        "post_minute": 30,
        "timezone": "America/Chicago",
    }


def _default_suggestions() -> Dict[str, Any]:
    return {"channel_id": None}


def _default_boost() -> Dict[str, Any]:
    return {"enabled": False, "channel_id": None}


def _default_guide() -> Dict[str, Any]:
    return {
        "enabled": True,
        "channel_id": None,
    }


def _default_embed() -> Dict[str, Any]:
    return {
        "enabled": False,
        "default_color": None,
        "role_tier": {},
        "description_limits": {"default_limit": 500, "limits": {}},
        "color_tiers": {},
        "feature_access": {},
    }


# Exported for consumers that imported DEFAULT_CONFIG from storage.config_manager
DEFAULT_CONFIG = {
    "roles": _default_roles(),
    "server": _default_server(),
    "wyr": _default_wyr(),
    "new_members": _default_new_members(),
    "announcement": _default_announcement(),
    "tag_tracker": _default_tag_tracker(),
    "drops": _default_drops(),
    "suggestions": _default_suggestions(),
    "boost": _default_boost(),
    "guide": _default_guide(),
    "embed": _default_embed(),
    "setup_complete": False,
    "color_tiers_seeded": False,
}


def _as_int_id_list(values: Any) -> List[int]:
    """Coerce a list of Discord IDs to ints, dropping anything non-numeric.

    Role/channel IDs can arrive as ints (bot writes) or numeric strings (some
    dashboard/older docs). Normalizing once here means every bot-side consumer
    (permission checks like create_embed / whitelist, ``guild.get_role``) compares
    like-typed ints without each call site having to re-coerce.
    """
    out: List[int] = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────────
# GuildConfig dataclass — structured per-guild settings
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GuildConfig:
    """Represents configuration for a single guild."""
    guild_id: int
    roles: Dict[str, Any]        = field(default_factory=_default_roles)
    server: Dict[str, Any]       = field(default_factory=_default_server)
    wyr: Dict[str, Any]          = field(default_factory=_default_wyr)
    new_members: Dict[str, Any]  = field(default_factory=_default_new_members)
    announcement: Dict[str, Any] = field(default_factory=_default_announcement)
    tag_tracker: Dict[str, Any]  = field(default_factory=_default_tag_tracker)
    drops: Dict[str, Any]        = field(default_factory=_default_drops)
    suggestions: Dict[str, Any]  = field(default_factory=_default_suggestions)
    boost: Dict[str, Any]        = field(default_factory=_default_boost)
    guide: Dict[str, Any]        = field(default_factory=_default_guide)
    embed: Dict[str, Any]        = field(default_factory=_default_embed)
    setup_complete: bool         = False
    color_tiers_seeded: bool     = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "guild_id": self.guild_id,
            "roles": self.roles,
            "server": self.server,
            "wyr": self.wyr,
            "new_members": self.new_members,
            "announcement": self.announcement,
            "tag_tracker": self.tag_tracker,
            "drops": self.drops,
            "suggestions": self.suggestions,
            "boost": self.boost,
            "guide": self.guide,
            "embed": self.embed,
            "setup_complete": self.setup_complete,
            "color_tiers_seeded": self.color_tiers_seeded,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuildConfig":
        """Create from a database document (current feature-centric schema)."""
        # ── roles ──────────────────────────────────────────────────────
        # Normalize the permission-role lists to ints so downstream membership
        # checks (create_embed, whitelist, is_admin_role) are type-consistent
        # regardless of how the ids were stored.
        stored = data.get("roles") or {}
        roles = {
            "admin_role_ids": _as_int_id_list(stored.get("admin_role_ids")),
            "mod_role_ids": _as_int_id_list(stored.get("mod_role_ids")),
            "tiers": stored.get("tiers", {}),
        }

        # ── server ─────────────────────────────────────────────────────
        stored = data.get("server") or {}
        server = {"admin_channel_id": stored.get("admin_channel_id")}

        # ── wyr ────────────────────────────────────────────────────────
        dw = _default_wyr()
        stored = data.get("wyr") or {}
        wyr = {
            "channel_id": stored.get("channel_id"),
            "ping_role_id": stored.get("ping_role_id"),
            "post_hour": stored.get("post_hour", dw["post_hour"]),
            "post_minute": stored.get("post_minute", dw["post_minute"]),
            "timezone": stored.get("timezone", dw["timezone"]),
            "default_category": stored.get("default_category", dw["default_category"]),
            "thread_name_format": stored.get("thread_name_format", dw["thread_name_format"]),
            "thread_starter_message": stored.get("thread_starter_message", dw["thread_starter_message"]),
            "thread_auto_archive": stored.get("thread_auto_archive", dw["thread_auto_archive"]),
            "mapping_cleanup_days": stored.get("mapping_cleanup_days", dw["mapping_cleanup_days"]),
            "skip_initial_post": stored.get("skip_initial_post", dw["skip_initial_post"]),
        }
        wyr["enabled"] = stored["enabled"] if "enabled" in stored else bool(wyr["channel_id"])

        # ── new_members ────────────────────────────────────────────────
        stored = data.get("new_members") or {}
        nm_welcome_ch = stored.get("welcome_channel_id")
        nm_whitelist_role = stored.get("whitelist_role_id")
        new_members = {
            "enabled": stored["enabled"] if "enabled" in stored else bool(nm_welcome_ch or nm_whitelist_role),
            "account_age_requirement_days": stored.get("account_age_requirement_days", 90),
            "auto_kick": stored.get("auto_kick", True),
            "welcome_channel_id": nm_welcome_ch,
            "whitelist_role_id": nm_whitelist_role,
            "whitelist_enabled": stored.get("whitelist_enabled", True),
            "whitelist_role_name": stored.get("whitelist_role_name", "Whitelisted New Member"),
            "welcome_message_enabled": stored.get("welcome_message_enabled", True),
            "welcome_components": stored.get("welcome_components"),
        }

        # ── announcement ───────────────────────────────────────────────
        stored = data.get("announcement") or {}
        ann = {
            "channel_id": stored.get("channel_id"),
            "thread_auto_create": stored.get("thread_auto_create", True),
            "thread_name_format": stored.get("thread_name_format", "💬 {message_content}"),
            "thread_auto_archive_duration": stored.get("thread_auto_archive_duration", 1440),
            "thread_welcome_message": stored.get("thread_welcome_message", "💬 **Discussion Thread**\n\nDiscuss this announcement here!"),
            "auto_delete_threads": stored.get("auto_delete_threads", True),
        }

        # ── tag_tracker ────────────────────────────────────────────────
        stored = data.get("tag_tracker") or {}
        tag_tracker = {
            "enabled": stored.get("enabled", False),
            "server_tag": stored.get("server_tag"),
            "role_id": stored.get("role_id"),
        }

        # ── drops ──────────────────────────────────────────────────────
        _drops_defaults = _default_drops()
        stored = data.get("drops") or {}
        drops = {
            "channel_id": stored.get("channel_id"),
            "tracker_channels": stored.get("tracker_channels", {"Updates": None, "Free": None, "Prime": None}),
            "manager_role_id": stored.get("manager_role_id"),
            "post_hour": stored.get("post_hour", _drops_defaults["post_hour"]),
            "post_minute": stored.get("post_minute", _drops_defaults["post_minute"]),
            "timezone": stored.get("timezone", _drops_defaults["timezone"]),
        }
        if "enabled" in stored:
            drops["enabled"] = stored["enabled"]
        else:
            drops["enabled"] = bool(drops["channel_id"] or any(drops["tracker_channels"].values()))

        # ── suggestions ────────────────────────────────────────────────
        stored = data.get("suggestions") or {}
        suggestions = {"channel_id": stored.get("channel_id")}

        # ── boost ──────────────────────────────────────────────────────
        stored = data.get("boost") or {}
        boost = {"channel_id": stored.get("channel_id")}
        boost["enabled"] = stored["enabled"] if "enabled" in stored else bool(boost["channel_id"])

        # ── guide ──────────────────────────────────────────────────────
        dg = _default_guide()
        stored = data.get("guide") or {}
        guide = {
            "enabled": stored.get("enabled", dg["enabled"]),
            "channel_id": stored.get("channel_id", dg["channel_id"]),
        }

        # ── embed ──────────────────────────────────────────────────────
        stored = data.get("embed") or {}
        embed = {
            "default_color": stored.get("default_color"),
            "role_tier": stored.get("role_tier", {}),
            "description_limits": stored.get("description_limits", {"default_limit": 500, "limits": {}}),
            "color_tiers": stored.get("color_tiers", {}),
            "feature_access": stored.get("feature_access", {}),
        }
        embed["enabled"] = stored["enabled"] if "enabled" in stored else bool(embed["role_tier"])

        return cls(
            guild_id=data.get("guild_id"),
            roles=roles,
            server=server,
            wyr=wyr,
            new_members=new_members,
            announcement=ann,
            tag_tracker=tag_tracker,
            drops=drops,
            suggestions=suggestions,
            boost=boost,
            guide=guide,
            embed=embed,
            setup_complete=bool(data.get("setup_complete", False)),
            color_tiers_seeded=bool(data.get("color_tiers_seeded", False)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def is_admin_role(self, role_id: int) -> bool:
        """Check if a role ID is an admin role."""
        return role_id in self.roles["admin_role_ids"]

    def is_moderator_role(self, role_id: int) -> bool:
        """Check if a role ID is a moderator role."""
        return role_id in self.roles["mod_role_ids"]

    def is_staff_role(self, role_id: int) -> bool:
        """Check if a role ID is admin or moderator."""
        return self.is_admin_role(role_id) or self.is_moderator_role(role_id)

    def get_all_tier_role_ids(self) -> List[int]:
        """Get list of all configured tier role IDs."""
        return [int(k) for k in self.roles["tiers"].keys()]


# ─────────────────────────────────────────────────────────────────────────────
# GuildConfigManager — unified structured + flat settings
# ─────────────────────────────────────────────────────────────────────────────

class GuildConfigManager:
    """
    Manages per-guild configuration.

    All feature settings (WYR, new members, embed, etc.) live in the
    structured GuildConfig dataclass, loaded/saved with get_config() /
    save_config().

    Flat key-value settings (legacy or miscellaneous) can still be
    accessed via get_setting() / set_setting() for any remaining callers.
    Both share the ``settings_guild_config`` collection.
    """

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._cache: Dict[int, GuildConfig] = {}
        self._cache_time: Dict[int, datetime] = {}
        # Last time we verified a cached config against the DB's updated_at.
        # Within _cache_grace_seconds we trust the in-memory copy and skip the
        # per-call Mongo round-trip (hot paths: member joins, the WYR tick, the
        # tag loop). Bot-side writes update the cache directly; only external
        # (dashboard) edits take up to this long to propagate.
        self._cache_checked: Dict[int, datetime] = {}
        self._cache_grace_seconds = 30
        self._settings_cache: Dict[int, Dict] = {}
        self._collection = None
        self._initialized = False
        self._cache_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the manager and connect to the collection."""
        if self._initialized:
            return
        try:
            self._collection = self.db_manager.get_collection_manager('settings_guild_config')
            self._initialized = True
            logger.info("GuildConfigManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GuildConfigManager: {e}", exc_info=True)
            raise

    # ── Structured config ────────────────────────────────────────────────────

    async def get_config(self, guild_id: int, use_cache: bool = True) -> GuildConfig:
        """Get the structured configuration for a guild."""
        if not self._initialized:
            await self.initialize()

        if use_cache and guild_id in self._cache:
            # Check if DB has been updated externally (e.g. by dashboard)
            now = datetime.now(timezone.utc)
            cache_ts = self._cache_time.get(guild_id)
            last_check = self._cache_checked.get(guild_id)
            # Within the grace window, trust the in-memory copy and skip the
            # staleness probe that otherwise made every "cache hit" a DB call.
            if last_check and (now - last_check).total_seconds() < self._cache_grace_seconds:
                return self._cache[guild_id]
            if cache_ts:
                doc_meta = await self._collection.find_one(
                    {"guild_id": guild_id}, projection={"updated_at": 1}
                )
                self._cache_checked[guild_id] = now
                db_updated = doc_meta.get("updated_at") if doc_meta else None
                if db_updated and isinstance(db_updated, datetime):
                    if db_updated.tzinfo is None:
                        db_updated = db_updated.replace(tzinfo=timezone.utc)
                    if db_updated > cache_ts:
                        logger.debug(f"Config stale for guild {guild_id}, refetching")
                    else:
                        logger.debug(f"Cache hit for guild {guild_id}")
                        return self._cache[guild_id]
                else:
                    logger.debug(f"Cache hit for guild {guild_id}")
                    return self._cache[guild_id]
            else:
                return self._cache[guild_id]

        try:
            doc = await self._collection.find_one({"guild_id": guild_id})

            if doc:
                config = GuildConfig.from_dict(doc)
                # Snapshot the loaded state so save_config can write only the leaves
                # THIS caller changes (see BUG-C1 / _config_update_ops).
                config._loaded_snapshot = copy.deepcopy(config.to_dict())
                async with self._cache_lock:
                    self._settings_cache[guild_id] = {
                        k: v for k, v in doc.items() if k not in _STRUCTURED_KEYS
                    }
                logger.debug(f"Loaded config from database for guild {guild_id}")
            else:
                config = GuildConfig(guild_id=guild_id)
                # No persisted baseline -> save_config falls back to a full write.
                config._loaded_snapshot = None
                async with self._cache_lock:
                    self._settings_cache.setdefault(guild_id, {})
                logger.debug(f"Using default config for unconfigured guild {guild_id}")

            async with self._cache_lock:
                now = datetime.now(timezone.utc)
                self._cache[guild_id] = config
                self._cache_time[guild_id] = now
                self._cache_checked[guild_id] = now

            return config

        except Exception as e:
            logger.error(f"Error fetching config for guild {guild_id}: {e}", exc_info=True)
            return GuildConfig(guild_id=guild_id)

    async def save_config(self, config: GuildConfig) -> bool:
        """Save a guild's structured configuration to the database."""
        if not self._initialized:
            await self.initialize()

        try:
            now = datetime.now(timezone.utc)
            existing = await self._collection.find_one({"guild_id": config.guild_id})
            snapshot = getattr(config, "_loaded_snapshot", None)

            if existing:
                config.updated_at = now
                new_doc = config.to_dict()
                if snapshot is not None:
                    # Surgical save: write only the leaves this caller actually changed
                    # relative to what it loaded, so we never clobber a concurrent
                    # dashboard edit to an unrelated field back to a stale value.
                    sets, unsets = _config_update_ops(snapshot, new_doc)
                    # created_at is insert-only; guild_id never changes.
                    for immutable in ("created_at", "guild_id"):
                        sets.pop(immutable, None)
                        unsets.pop(immutable, None)
                    sets["updated_at"] = now
                    update: Dict[str, Any] = {"$set": sets}
                    if unsets:
                        update["$unset"] = unsets
                    await self._collection.update_one({"guild_id": config.guild_id}, update)
                else:
                    # No baseline to diff against: fall back to a full write, but never
                    # $set created_at (a default-constructed config would blank it).
                    new_doc.pop("created_at", None)
                    await self._collection.update_one(
                        {"guild_id": config.guild_id},
                        {"$set": new_doc},
                    )
                logger.info(f"Updated config for guild {config.guild_id}")
            else:
                config.created_at = now
                config.updated_at = now
                await self._collection.create_one(config.to_dict())
                logger.info(f"Created config for guild {config.guild_id}")

            async with self._cache_lock:
                saved_at = datetime.now(timezone.utc)
                self._cache[config.guild_id] = config
                self._cache_time[config.guild_id] = saved_at
                self._cache_checked[config.guild_id] = saved_at
                # Re-baseline: subsequent saves of this same object diff against the
                # state we just persisted.
                config._loaded_snapshot = copy.deepcopy(config.to_dict())

            return True

        except Exception as e:
            logger.error(f"Error saving config for guild {config.guild_id}: {e}", exc_info=True)
            return False

    # ── Flat settings (legacy / miscellaneous) ───────────────────────────────

    async def _load_settings_cache(self, guild_id: int) -> None:
        """Load flat settings from DB into _settings_cache for a guild."""
        try:
            doc = await self._collection.find_one({"guild_id": guild_id})
            async with self._cache_lock:
                if doc:
                    self._settings_cache[guild_id] = {
                        k: v for k, v in doc.items() if k not in _STRUCTURED_KEYS
                    }
                else:
                    self._settings_cache[guild_id] = {}
        except Exception as e:
            logger.error(f"Error loading settings cache for guild {guild_id}: {e}", exc_info=True)
            async with self._cache_lock:
                self._settings_cache[guild_id] = {}

    # A dotted flat key ("a.b") is written to Mongo as a nested path -- i.e.
    # {"$set": {"a.b": v}} stores {"a": {"b": v}}. The in-memory cache is rebuilt
    # straight from that raw doc on reload, so it must mirror the same nested
    # shape; otherwise a value written under a literal "a.b" cache key is lost on
    # the next reload and reads fall through to the default. These helpers keep
    # the cache representation consistent with Mongo for dotted keys.
    @staticmethod
    def _dotted_get(doc: Dict[str, Any], dotted_key: str) -> Tuple[bool, Any]:
        """Return (found, value) by traversing nested dicts along a dotted key."""
        cur: Any = doc
        for part in dotted_key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return False, None
        return True, cur

    @staticmethod
    def _dotted_set(doc: Dict[str, Any], dotted_key: str, value: Any) -> None:
        """Set a value into nested dicts, creating intermediate dicts as needed."""
        parts = dotted_key.split(".")
        cur = doc
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value

    @staticmethod
    def _dotted_unset(doc: Dict[str, Any], dotted_key: str) -> None:
        """Remove a nested key along a dotted path; no-op if the path is absent."""
        parts = dotted_key.split(".")
        cur = doc
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                return
            cur = nxt
        cur.pop(parts[-1], None)

    async def get_setting(self, key: str, guild_id: int, default: Any = None) -> Any:
        """Get a per-guild flat setting. Dotted keys traverse the nested shape
        MongoDB stores them under, so the value survives a cache reload."""
        if not self._initialized:
            await self.initialize()
        if guild_id not in self._settings_cache:
            await self._load_settings_cache(guild_id)
        cache = self._settings_cache[guild_id]
        if "." in key:
            found, val = self._dotted_get(cache, key)
            if found:
                return val
            return DEFAULT_SETTINGS.get(key, default)
        return cache.get(key, DEFAULT_SETTINGS.get(key, default))

    async def set_setting(self, key: str, value: Any, guild_id: int) -> bool:
        """Set a per-guild flat setting using MongoDB $set."""
        if not self._initialized:
            await self.initialize()
        try:
            now = datetime.now(timezone.utc)
            await self._collection.update_one(
                {"guild_id": guild_id},
                {
                    "$set": {key: value},
                    "$setOnInsert": {"guild_id": guild_id, "created_at": now},
                },
                upsert=True,
            )
            async with self._cache_lock:
                cache = self._settings_cache.setdefault(guild_id, {})
                if "." in key:
                    self._dotted_set(cache, key, value)
                else:
                    cache[key] = value
            return True
        except Exception as e:
            logger.error(f"Error setting '{key}' for guild {guild_id}: {e}", exc_info=True)
            return False

    async def unset_setting(self, key: str, guild_id: int) -> bool:
        """Remove a per-guild flat setting via MongoDB ``$unset`` (so it reads back as
        its default, rather than being stored as an explicit ``null``)."""
        if not self._initialized:
            await self.initialize()
        try:
            await self._collection.update_one(
                {"guild_id": guild_id},
                {"$unset": {key: ""}},
            )
            async with self._cache_lock:
                cache = self._settings_cache.get(guild_id, {})
                if "." in key:
                    self._dotted_unset(cache, key)
                else:
                    cache.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Error unsetting '{key}' for guild {guild_id}: {e}", exc_info=True)
            return False

    async def set_many_settings(self, settings: Dict[str, Any], guild_id: int) -> bool:
        """Set multiple per-guild flat settings atomically."""
        if not self._initialized:
            await self.initialize()
        try:
            now = datetime.now(timezone.utc)
            await self._collection.update_one(
                {"guild_id": guild_id},
                {
                    "$set": settings,
                    "$setOnInsert": {"guild_id": guild_id, "created_at": now},
                },
                upsert=True,
            )
            async with self._cache_lock:
                cache = self._settings_cache.setdefault(guild_id, {})
                for k, v in settings.items():
                    if "." in k:
                        self._dotted_set(cache, k, v)
                    else:
                        cache[k] = v
            return True
        except Exception as e:
            logger.error(f"Error setting multiple settings for guild {guild_id}: {e}", exc_info=True)
            return False

    # ── Nested helpers (utility) ─────────────────────────────────────────────

    async def get_nested(self, parent_key: str, sub_key: str, guild_id: int, default: Any = None) -> Any:
        """Get a nested flat setting value."""
        parent = await self.get_setting(parent_key, guild_id, {})
        if isinstance(parent, dict):
            return parent.get(sub_key, default)
        return default

    async def set_nested(self, parent_key: str, sub_key: str, value: Any, guild_id: int) -> bool:
        """Set a nested flat setting using MongoDB dot-notation $set."""
        dot_key = f"{parent_key}.{sub_key}"
        if not self._initialized:
            await self.initialize()
        try:
            now = datetime.now(timezone.utc)
            await self._collection.update_one(
                {"guild_id": guild_id},
                {
                    "$set": {dot_key: value},
                    "$setOnInsert": {"guild_id": guild_id, "created_at": now},
                },
                upsert=True,
            )
            async with self._cache_lock:
                cache = self._settings_cache.setdefault(guild_id, {})
                if parent_key not in cache or not isinstance(cache[parent_key], dict):
                    cache[parent_key] = {}
                cache[parent_key][sub_key] = value
            return True
        except Exception as e:
            logger.error(f"Error setting nested '{dot_key}' for guild {guild_id}: {e}", exc_info=True)
            return False

    # ── Structured-config helpers ────────────────────────────────────────────

    async def set_channel(self, guild_id: int, channel_type: str, channel_id: Optional[int]) -> bool:
        """Set a channel ID for a guild via the feature-centric config."""
        _channel_map = {
            "welcome":      ("new_members", "welcome_channel_id"),
            "suggestions":  ("suggestions", "channel_id"),
            "admin":        ("server", "admin_channel_id"),
            "drops":        ("drops", "channel_id"),
            "wyr":          ("wyr", "channel_id"),
            "announcement": ("announcement", "channel_id"),
            "boost_log":    ("boost", "channel_id"),
            "guide":        ("guide", "channel_id"),
        }
        if channel_type not in _channel_map:
            logger.warning(f"Invalid channel type: {channel_type}")
            return False
        feature, key = _channel_map[channel_type]
        config = await self.get_config(guild_id)
        getattr(config, feature)[key] = channel_id
        return await self.save_config(config)

    async def set_role(self, guild_id: int, role_type: str, role_id: int, action: str = "add") -> bool:
        """Add or remove a global permission role (admin or moderator)."""
        config = await self.get_config(guild_id)

        if role_type == "admin":
            if action == "add" and role_id not in config.roles["admin_role_ids"]:
                config.roles["admin_role_ids"].append(role_id)
            elif action == "remove" and role_id in config.roles["admin_role_ids"]:
                config.roles["admin_role_ids"].remove(role_id)
        elif role_type == "moderator":
            if action == "add" and role_id not in config.roles["mod_role_ids"]:
                config.roles["mod_role_ids"].append(role_id)
            elif action == "remove" and role_id in config.roles["mod_role_ids"]:
                config.roles["mod_role_ids"].remove(role_id)
        else:
            logger.warning(f"Invalid role type: {role_type}")
            return False

        return await self.save_config(config)

    async def invalidate_cache(self, guild_id: int) -> None:
        """Remove a guild from all caches, forcing fresh fetches."""
        async with self._cache_lock:
            self._cache.pop(guild_id, None)
            self._cache_time.pop(guild_id, None)
            self._cache_checked.pop(guild_id, None)
            self._settings_cache.pop(guild_id, None)
            logger.debug(f"Cache invalidated for guild {guild_id}")

    async def clear_cache(self) -> None:
        """Clear all cached configs and settings."""
        async with self._cache_lock:
            self._cache.clear()
            self._cache_time.clear()
            self._cache_checked.clear()
            self._settings_cache.clear()
            logger.info("All guild config cache cleared")

    async def get_all_configured_guilds(self) -> List[int]:
        """Get list of all guild IDs that have been configured."""
        if not self._initialized:
            await self.initialize()
        try:
            docs = await self._collection.find_many({})
            return [doc["guild_id"] for doc in docs if "guild_id" in doc]
        except Exception as e:
            logger.error(f"Error fetching configured guilds: {e}", exc_info=True)
            return []

    def has_staff_role(self, config: GuildConfig, user_role_ids: Set[int]) -> bool:
        """Check if any of the user's roles are admin or moderator roles."""
        admin_set = set(config.roles["admin_role_ids"])
        mod_set = set(config.roles["mod_role_ids"])
        return bool(user_role_ids & (admin_set | mod_set))

    def has_admin_role(self, config: GuildConfig, user_role_ids: Set[int]) -> bool:
        """Check if any of the user's roles are admin roles."""
        admin_set = set(config.roles["admin_role_ids"])
        return bool(user_role_ids & admin_set)

    # ── Typed accessors — Embed Config (async) ───────────────────────────────

    async def embed_description_limits(self, guild_id: int) -> Dict[str, Any]:
        config = await self.get_config(guild_id)
        return config.embed.get("description_limits", {"default_limit": 500, "limits": {}})

    async def embed_color_tiers(self, guild_id: int) -> Dict[str, Dict[str, str]]:
        config = await self.get_config(guild_id)
        return config.embed.get("color_tiers", {})

    async def embed_feature_access(self, guild_id: int) -> Dict[str, list]:
        config = await self.get_config(guild_id)
        return config.embed.get("feature_access", {})

    async def setup_complete(self, guild_id: int) -> bool:
        config = await self.get_config(guild_id)
        return config.setup_complete

    # ── Typed accessors — WYR Config (async) ─────────────────────────────────

    async def wyr_post_hour(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.wyr.get("post_hour", 6)

    async def wyr_post_minute(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.wyr.get("post_minute", 0)

    async def wyr_timezone(self, guild_id: int) -> str:
        config = await self.get_config(guild_id)
        return config.wyr.get("timezone", "America/Chicago")

    async def wyr_default_category(self, guild_id: int) -> str:
        config = await self.get_config(guild_id)
        return config.wyr.get("default_category", "sfw")

    async def wyr_thread_name_format(self, guild_id: int) -> str:
        config = await self.get_config(guild_id)
        return config.wyr.get("thread_name_format", _default_wyr()["thread_name_format"])

    async def wyr_thread_starter_message(self, guild_id: int) -> str:
        config = await self.get_config(guild_id)
        return config.wyr.get("thread_starter_message", _default_wyr()["thread_starter_message"])

    async def wyr_thread_auto_archive(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.wyr.get("thread_auto_archive", 1440)

    async def wyr_mapping_cleanup_days(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.wyr.get("mapping_cleanup_days", 30)

    # ── Typed accessors (sync, from cache only) ───────────────────────────────

    def get_sync(self, key: str, guild_id: int, default: Any = None) -> Any:
        """Get a flat setting synchronously from cache (does NOT hit the DB)."""
        cache = self._settings_cache.get(guild_id, {})
        return cache.get(key, DEFAULT_SETTINGS.get(key, default))

    def embed_description_limits_sync(self, guild_id: int) -> Dict[str, Any]:
        config = self._cache.get(guild_id)
        if config:
            return config.embed.get("description_limits", {"default_limit": 500, "limits": {}})
        return {"default_limit": 500, "limits": {}}

    def embed_color_tiers_sync(self, guild_id: int) -> Dict[str, Dict[str, str]]:
        config = self._cache.get(guild_id)
        if config:
            return config.embed.get("color_tiers", {})
        return {}

    def embed_feature_access_sync(self, guild_id: int) -> Dict[str, list]:
        config = self._cache.get(guild_id)
        if config:
            return config.embed.get("feature_access", {})
        return {}

    def setup_complete_sync(self, guild_id: int) -> bool:
        config = self._cache.get(guild_id)
        if config:
            return config.setup_complete
        return False

    def wyr_post_hour_sync(self, guild_id: int) -> int:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("post_hour", 6)
        return 6

    def wyr_post_minute_sync(self, guild_id: int) -> int:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("post_minute", 0)
        return 0

    def wyr_timezone_sync(self, guild_id: int) -> str:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("timezone", "America/Chicago")
        return "America/Chicago"

    def wyr_default_category_sync(self, guild_id: int) -> str:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("default_category", "sfw")
        return "sfw"

    def wyr_thread_name_format_sync(self, guild_id: int) -> str:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("thread_name_format", _default_wyr()["thread_name_format"])
        return _default_wyr()["thread_name_format"]

    def wyr_thread_starter_message_sync(self, guild_id: int) -> str:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("thread_starter_message", _default_wyr()["thread_starter_message"])
        return _default_wyr()["thread_starter_message"]

    def wyr_thread_auto_archive_sync(self, guild_id: int) -> int:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("thread_auto_archive", 1440)
        return 1440

    def wyr_mapping_cleanup_days_sync(self, guild_id: int) -> int:
        config = self._cache.get(guild_id)
        if config:
            return config.wyr.get("mapping_cleanup_days", 30)
        return 30


# ─────────────────────────────────────────────────────────────────────────────
# Global instance + accessor functions
# ─────────────────────────────────────────────────────────────────────────────

_guild_config_manager: Optional[GuildConfigManager] = None


async def get_guild_config_manager(db_manager=None) -> GuildConfigManager:
    """Get or create the global GuildConfigManager instance."""
    global _guild_config_manager
    if _guild_config_manager is None:
        if db_manager is None:
            raise ValueError("db_manager is required for first initialization")
        _guild_config_manager = GuildConfigManager(db_manager)
        await _guild_config_manager.initialize()
    return _guild_config_manager


async def get_config(guild_id: int) -> GuildConfig:
    """Convenience function to get structured config for a guild."""
    manager = await get_guild_config_manager()
    return await manager.get_config(guild_id)


async def get_config_manager() -> GuildConfigManager:
    """Alias for get_guild_config_manager() used by the admin-panel bindings."""
    return await get_guild_config_manager()
