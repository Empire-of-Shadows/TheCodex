"""
Unified Guild Configuration Manager for TheCodex Bot

Feature-centric schema: each feature owns its channel ID, role ID, and
settings in one place.  Cross-feature identifiers (admin/moderator roles,
server admin channel) remain at the top level.

Structured fields are managed through GuildConfig / save_config().
Flat settings (legacy or miscellaneous) can still be written through
get_setting() / set_setting() for any remaining callers, but all WYR
and embed settings are now fully absorbed into the structured config.

Storage goes through the engine ``GuildConfigStore`` over the
``settings_guild_config`` collection manager: reads are hit-first cached
by the manager (30s TTL, copy-on-read), writes are surgical dotted
``$set``/``$unset`` that invalidate the cache, and ``guild_id`` is the
canonical STRING form at the storage boundary (int callers are coerced).
The stored documents were normalized int -> str by migration
``m4_guildconfig_guild_id_to_str``; this module must not ship ahead of
that migration being applied.
"""

import copy
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from storage.config.guild_config_store import GuildConfigStore
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
# Per-guild flat setting defaults  (kept minimal - most settings are structured)
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
        # Offer the ping role to members who interact with a question and do
        # not already have it. Off means the role stays available through
        # /wyr notify and the post button, just never advertised.
        "subscribe_prompt_enabled": True,
    }


def _default_new_members() -> Dict[str, Any]:
    return {
        "enabled": False,
        "account_age_requirement_days": 90,
        "auto_kick": True,
        "greeting_channel_id": None,
        "whitelist_role_id": None,
        "whitelist_enabled": True,
        "whitelist_role_name": "Whitelisted New Member",
        "greeting_enabled": True,
        "greeting_components": None,
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


def _merge_unknown_keys(built: Dict[str, Any], stored: Dict[str, Any]) -> Dict[str, Any]:
    """Carry through stored subkeys ``from_dict`` does not model.

    Sections are rebuilt from their known keys; without this, a subkey written by a
    newer panel leaf (or any future structured write) would vanish from memory on
    reload and never round-trip through ``save_config``. Unknown keys are preserved
    verbatim so load -> save is lossless and nothing needs whitelisting to survive.
    """
    for k, v in stored.items():
        if k not in built:
            built[k] = v
    return built


# ─────────────────────────────────────────────────────────────────────────────
# GuildConfig dataclass - structured per-guild settings
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GuildConfig:
    """Represents configuration for a single guild.

    ``guild_id`` is held (and stored) in the canonical STRING form; the
    ``__post_init__`` coercion accepts int-passing callers."""
    guild_id: str
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

    def __post_init__(self):
        if self.guild_id is not None:
            self.guild_id = str(self.guild_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage.

        The permission role lists are serialized as STRINGS (the storage-canonical
        form, matching migration m9); ``from_dict`` coerces them back to ints for
        in-memory comparisons against discord.py's int role ids."""
        roles = dict(self.roles)
        roles["admin_role_ids"] = [str(r) for r in roles.get("admin_role_ids") or []]
        roles["mod_role_ids"] = [str(r) for r in roles.get("mod_role_ids") or []]
        return {
            "guild_id": self.guild_id,
            "roles": roles,
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
        """Create from a database document (current feature-centric schema).

        Every section preserves subkeys it does not model (``_merge_unknown_keys``),
        so a structured key written by a newer panel leaf survives reload and
        round-trips through ``save_config`` without being whitelisted here.
        Top-level keys outside the dataclass (the flat get_setting/set_setting
        namespace) are deliberately not modeled; the diff-based save never
        touches them."""
        # ── roles ──────────────────────────────────────────────────────
        # Normalize the permission-role lists to ints so downstream membership
        # checks (create_embed, whitelist, is_admin_role) are type-consistent
        # regardless of how the ids were stored.
        stored = data.get("roles") or {}
        roles = _merge_unknown_keys({
            "admin_role_ids": _as_int_id_list(stored.get("admin_role_ids")),
            "mod_role_ids": _as_int_id_list(stored.get("mod_role_ids")),
        }, stored)

        # ── server ─────────────────────────────────────────────────────
        stored = data.get("server") or {}
        server = _merge_unknown_keys({"admin_channel_id": stored.get("admin_channel_id")}, stored)

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
            "subscribe_prompt_enabled": stored.get(
                "subscribe_prompt_enabled", dw["subscribe_prompt_enabled"]
            ),
        }
        wyr = _merge_unknown_keys(wyr, stored)
        wyr["enabled"] = stored["enabled"] if "enabled" in stored else bool(wyr["channel_id"])

        # ── new_members ────────────────────────────────────────────────
        stored = data.get("new_members") or {}
        nm_greeting_ch = stored.get("greeting_channel_id")
        nm_whitelist_role = stored.get("whitelist_role_id")
        new_members = {
            "enabled": stored["enabled"] if "enabled" in stored else bool(nm_greeting_ch or nm_whitelist_role),
            "account_age_requirement_days": stored.get("account_age_requirement_days", 90),
            "auto_kick": stored.get("auto_kick", True),
            "greeting_channel_id": nm_greeting_ch,
            "whitelist_role_id": nm_whitelist_role,
            "whitelist_enabled": stored.get("whitelist_enabled", True),
            "whitelist_role_name": stored.get("whitelist_role_name", "Whitelisted New Member"),
            "greeting_enabled": stored.get("greeting_enabled", True),
            "greeting_components": stored.get("greeting_components"),
        }
        new_members = _merge_unknown_keys(new_members, stored)

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
        ann = _merge_unknown_keys(ann, stored)

        # ── tag_tracker ────────────────────────────────────────────────
        stored = data.get("tag_tracker") or {}
        tag_tracker = _merge_unknown_keys({
            "enabled": stored.get("enabled", False),
            "server_tag": stored.get("server_tag"),
            "role_id": stored.get("role_id"),
        }, stored)

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
        drops = _merge_unknown_keys(drops, stored)
        if "enabled" in stored:
            drops["enabled"] = stored["enabled"]
        else:
            drops["enabled"] = bool(drops["channel_id"] or any(drops["tracker_channels"].values()))

        # ── suggestions ────────────────────────────────────────────────
        stored = data.get("suggestions") or {}
        suggestions = _merge_unknown_keys({"channel_id": stored.get("channel_id")}, stored)

        # ── boost ──────────────────────────────────────────────────────
        stored = data.get("boost") or {}
        boost = _merge_unknown_keys({"channel_id": stored.get("channel_id")}, stored)
        boost["enabled"] = stored["enabled"] if "enabled" in stored else bool(boost["channel_id"])

        # ── guide ──────────────────────────────────────────────────────
        dg = _default_guide()
        stored = data.get("guide") or {}
        guide = _merge_unknown_keys({
            "enabled": stored.get("enabled", dg["enabled"]),
            "channel_id": stored.get("channel_id", dg["channel_id"]),
        }, stored)

        # ── embed ──────────────────────────────────────────────────────
        stored = data.get("embed") or {}
        embed = {
            "default_color": stored.get("default_color"),
            "role_tier": stored.get("role_tier", {}),
            "description_limits": stored.get("description_limits", {"default_limit": 500, "limits": {}}),
            "feature_access": stored.get("feature_access", {}),
        }
        embed = _merge_unknown_keys(embed, stored)
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
        """Every role id that Role Tier Mapping assigns to at least one tier.

        Reads ``embed.role_tier`` - the mapping the admin panel actually writes
        (``{role_id_str: [tier_name, ...]}``). This used to read ``roles.tiers``, a
        vestigial field from an older schema generation that nothing has written since
        the v2 collapse, so it always returned an empty list: members granted embed
        access purely through Role Tier Mapping silently failed the
        ``has_embed_permissions`` check. Removed from stored docs by migration m12.
        """
        out: List[int] = []
        for key in (self.embed.get("role_tier") or {}):
            try:
                out.append(int(key))
            except (TypeError, ValueError):
                logger.warning(f"Skipping non-numeric role_tier key: {key!r}")
        return out


# ─────────────────────────────────────────────────────────────────────────────
# GuildConfigManager - unified structured + flat settings
# ─────────────────────────────────────────────────────────────────────────────

class GuildConfigManager:
    """
    Manages per-guild configuration.

    All feature settings (WYR, new members, embed, etc.) live in the
    structured GuildConfig dataclass, loaded/saved with get_config() /
    save_config().

    Flat key-value settings (legacy or miscellaneous) can still be
    accessed via get_setting() / set_setting() for any remaining callers.
    Both share the ``settings_guild_config`` collection, reached through
    the engine ``GuildConfigStore`` (no second cache layer here: reads
    ride the collection manager's hit-first cache, writes invalidate it).
    """

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._collection = None
        self._store: Optional[GuildConfigStore] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the manager and connect to the collection."""
        if self._initialized:
            return
        try:
            self._collection = self.db_manager.get_collection_manager('settings_guild_config')
            # cache_ttl=30 preserves the old typed cache's 30s staleness bound for
            # external (dashboard) writes; bot-side writes through the manager
            # invalidate the cache immediately.
            self._store = GuildConfigStore(
                self._collection, id_field="guild_id", cache_ttl=30
            )
            self._initialized = True
            logger.info("GuildConfigManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GuildConfigManager: {e}", exc_info=True)
            raise

    # ── Structured config ────────────────────────────────────────────────────

    async def get_config(self, guild_id: int, use_cache: bool = True) -> GuildConfig:
        """Get the structured configuration for a guild.

        Each call returns a fresh ``GuildConfig`` built from the store's cached
        document (30s TTL, copy-on-read), so concurrent callers never share a
        mutable object and every instance carries its own save baseline."""
        if not self._initialized:
            await self.initialize()

        try:
            doc = await self._store.get_doc(guild_id, use_cache=use_cache)
            if doc:
                config = GuildConfig.from_dict(doc)
                # Snapshot the loaded state so save_config can write only the leaves
                # THIS caller changes (see BUG-C1 / _config_update_ops).
                config._loaded_snapshot = copy.deepcopy(config.to_dict())
            else:
                config = GuildConfig(guild_id=guild_id)
                # No persisted baseline -> save_config falls back to a full write.
                config._loaded_snapshot = None
                logger.debug(f"Using default config for unconfigured guild {guild_id}")
            return config

        except Exception as e:
            logger.error(f"Error fetching config for guild {guild_id}: {e}", exc_info=True)
            config = GuildConfig(guild_id=guild_id)
            config._loaded_snapshot = None
            return config

    async def save_config(self, config: GuildConfig) -> bool:
        """Save a guild's structured configuration to the database."""
        if not self._initialized:
            await self.initialize()

        gid = str(config.guild_id)
        try:
            existing = await self._store.get_doc(gid, use_cache=False)
            snapshot = getattr(config, "_loaded_snapshot", None)

            if existing:
                new_doc = config.to_dict()
                if snapshot is not None:
                    # Surgical save: write only the leaves this caller actually changed
                    # relative to what it loaded, so we never clobber a concurrent
                    # dashboard edit to an unrelated field back to a stale value.
                    # One atomic $set+$unset via store.apply.
                    sets, unsets = _config_update_ops(snapshot, new_doc)
                    # created_at is insert-only; guild_id never changes; updated_at
                    # is stamped by the CollectionManager on every write.
                    for managed in ("created_at", "guild_id", "updated_at"):
                        sets.pop(managed, None)
                        unsets.pop(managed, None)
                    if sets or unsets:
                        if not await self._store.apply(gid, sets, list(unsets)):
                            return False
                else:
                    # No baseline to diff against: fall back to a full write of the
                    # top-level sections, minus the managed fields (so a
                    # default-constructed config can never blank created_at).
                    payload = {
                        k: v for k, v in new_doc.items()
                        if k not in ("created_at", "updated_at", "guild_id")
                    }
                    if not await self._store.update(gid, payload, upsert=False):
                        return False
                logger.info(f"Updated config for guild {gid}")
            else:
                now = datetime.now(timezone.utc)
                config.created_at = now
                config.updated_at = now
                await self._collection.create_one(config.to_dict())
                logger.info(f"Created config for guild {gid}")

            # Re-baseline: subsequent saves of this same object diff against the
            # state we just persisted.
            config._loaded_snapshot = copy.deepcopy(config.to_dict())
            return True

        except Exception as e:
            logger.error(f"Error saving config for guild {gid}: {e}", exc_info=True)
            return False

    async def has_config(self, guild_id: int) -> bool:
        """True if a config document exists for the guild (unlike get_config,
        which fabricates a default for unconfigured guilds)."""
        if not self._initialized:
            await self.initialize()
        return await self._store.get_doc(guild_id) is not None

    # ── Flat settings (legacy / miscellaneous) ───────────────────────────────
    # Thin passthroughs to the store: dotted keys are handled natively (Mongo
    # ``$set`` on a dotted path stores the nested shape; the store's reader digs
    # the same shape back out), and every write invalidates the manager cache.
    # NOTE: unlike the old flat cache, the store reads the WHOLE document, so a
    # flat read of a structured head would return the section; callers route
    # structured paths through get_config (see admin/settings/bindings.py).

    async def get_setting(self, key: str, guild_id: int, default: Any = None) -> Any:
        """Get a per-guild flat setting (dotted keys traverse the nested shape)."""
        if not self._initialized:
            await self.initialize()
        return await self._store.get_setting(
            key, guild_id, DEFAULT_SETTINGS.get(key, default)
        )

    async def set_setting(self, key: str, value: Any, guild_id: int) -> bool:
        """Set a per-guild flat setting using MongoDB $set (upserts)."""
        if not self._initialized:
            await self.initialize()
        return await self._store.set_setting(key, value, guild_id)

    async def unset_setting(self, key: str, guild_id: int) -> bool:
        """Remove a per-guild flat setting via MongoDB ``$unset`` (so it reads back as
        its default, rather than being stored as an explicit ``null``)."""
        if not self._initialized:
            await self.initialize()
        # The store reports False for an already-absent key; that is a successful
        # unset from the caller's point of view (real errors are logged store-side).
        await self._store.unset(guild_id, [key])
        return True

    async def set_many_settings(self, settings: Dict[str, Any], guild_id: int) -> bool:
        """Set multiple per-guild flat settings in one write."""
        if not self._initialized:
            await self.initialize()
        return await self._store.set_many(settings, guild_id)

    # ── Nested helpers (utility) ─────────────────────────────────────────────

    async def get_nested(self, parent_key: str, sub_key: str, guild_id: int, default: Any = None) -> Any:
        """Get a nested flat setting value."""
        return await self.get_setting(f"{parent_key}.{sub_key}", guild_id, default)

    async def set_nested(self, parent_key: str, sub_key: str, value: Any, guild_id: int) -> bool:
        """Set a nested flat setting using MongoDB dot-notation $set."""
        return await self.set_setting(f"{parent_key}.{sub_key}", value, guild_id)

    # ── Structured-config helpers ────────────────────────────────────────────

    async def set_channel(self, guild_id: int, channel_type: str, channel_id: Optional[int]) -> bool:
        """Set a channel ID for a guild via the feature-centric config."""
        _channel_map = {
            "greeting":     ("new_members", "greeting_channel_id"),
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
        """Add or remove a global permission role (admin or moderator).

        Routed through the store's atomic ``$addToSet`` / ``$pull`` at the
        canonical ``roles.admin_role_ids`` / ``roles.mod_role_ids`` paths, so
        two concurrent role edits can never lose each other's update the way
        the old read-modify-write save could."""
        if not self._initialized:
            await self.initialize()
        kind = {"admin": "admin", "moderator": "mod"}.get(role_type)
        if kind is None:
            logger.warning(f"Invalid role type: {role_type}")
            return False
        if action == "add":
            return await self._store.add_role(guild_id, kind, role_id)
        if action == "remove":
            return await self._store.remove_role(guild_id, kind, role_id)
        logger.warning(f"Invalid role action: {action}")
        return False

    async def invalidate_cache(self, guild_id: int) -> None:
        """Drop the guild's cached document, forcing a fresh fetch."""
        if not self._initialized:
            await self.initialize()
        self._store.invalidate(guild_id)
        logger.debug(f"Cache invalidated for guild {guild_id}")

    async def clear_cache(self) -> None:
        """Clear every cached document for the config collection."""
        if not self._initialized:
            await self.initialize()
        self._store.clear()
        logger.info("All guild config cache cleared")

    async def get_all_configured_guilds(self) -> List[int]:
        """Get list of all configured guild IDs, as ints (bot-side callers hand
        them to ``bot.get_guild``; storage holds the canonical string form)."""
        if not self._initialized:
            await self.initialize()
        try:
            docs = await self._collection.find_many({}, projection={"guild_id": 1})
            out: List[int] = []
            for doc in docs:
                try:
                    out.append(int(doc["guild_id"]))
                except (KeyError, TypeError, ValueError):
                    continue
            return out
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

    # ── Typed accessors - Embed Config (async) ───────────────────────────────

    async def embed_description_limits(self, guild_id: int) -> Dict[str, Any]:
        config = await self.get_config(guild_id)
        return config.embed.get("description_limits", {"default_limit": 500, "limits": {}})

    async def embed_feature_access(self, guild_id: int) -> Dict[str, list]:
        config = await self.get_config(guild_id)
        return config.embed.get("feature_access", {})

    async def setup_complete(self, guild_id: int) -> bool:
        config = await self.get_config(guild_id)
        return config.setup_complete

    # ── Typed accessors - WYR Config (async) ─────────────────────────────────

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

    # NOTE: the old ``get_sync`` / ``*_sync`` cache-only accessors are gone with
    # the hand-rolled typed cache; they had no callers anywhere in the bot. New
    # hot paths read through the async accessors above (store-cached, 30s TTL).


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
