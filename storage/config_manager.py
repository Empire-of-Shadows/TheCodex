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
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from utils.logger import get_logger

logger = get_logger("GuildConfig")

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

# Legacy top-level keys to remove from existing documents on first save
_LEGACY_FIELDS: tuple = (
    "channels",
    "wyr_post_hour", "wyr_post_minute", "wyr_timezone",
    "wyr_default_category", "wyr_thread_name_format",
    "wyr_thread_starter_message", "wyr_thread_auto_archive",
    "wyr_mapping_cleanup_days",
    "embed_description_limits", "embed_color_tiers", "embed_feature_access",
    "embed_role_tier_mapping",
    # new_members text fields replaced by welcome_components JSON builder
    "welcome_header", "welcome_body", "welcome_channels_title",
)

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
        """Create from dictionary (database document).

        Handles three generations of documents transparently:
        - Gen3 (new feature-centric): wyr.channel_id, new_members.welcome_channel_id, etc.
        - Gen2 (nested channels/roles + flat WYR): channels.wyr, roles.wyr_ping, wyr_post_hour...
        - Gen1 (fully flat): wyr_channel_id, wyr_ping_role_id, etc.
        """
        # Generation detection
        # Gen3: has top-level "wyr" dict with "channel_id" key (no "channels" key)
        # Gen2: has top-level "channels" dict
        # Gen1: neither
        is_gen3 = (
            "wyr" in data
            and isinstance(data.get("wyr"), dict)
            and "channel_id" in data.get("wyr", {})
        )
        is_gen2 = "channels" in data and not is_gen3
        channels_g2 = data.get("channels", {}) if is_gen2 else {}
        roles_g2 = data.get("roles", {}) if is_gen2 else {}

        # ── roles ──────────────────────────────────────────────────────
        _old_tier_names = {"silver_fang", "golden_snake", "platinum_ghost", "diamond_wraith", "mystic_dragon"}
        if "roles" in data:
            stored = data["roles"]
            tiers_stored = stored.get("tiers", {})
            if set(tiers_stored.keys()) & _old_tier_names:
                tiers_stored = {}
            # Canonical keys are admin_role_ids / mod_role_ids; fall back to the
            # legacy admin / moderator names for documents not yet migrated.
            roles = {
                "admin_role_ids": stored.get("admin_role_ids", stored.get("admin", [])),
                "mod_role_ids": stored.get("mod_role_ids", stored.get("moderator", [])),
                "tiers": tiers_stored,
            }
        else:
            roles = {
                "admin_role_ids": data.get("admin_role_ids", []),
                "mod_role_ids": data.get("moderator_role_ids", []),
                "tiers": {},
            }

        # ── server ─────────────────────────────────────────────────────
        if "server" in data and isinstance(data["server"], dict):
            stored = data["server"]
            server = {"admin_channel_id": stored.get("admin_channel_id")}
        elif is_gen2:
            server = {"admin_channel_id": channels_g2.get("admin")}
        else:
            server = {"admin_channel_id": data.get("admin_channel_id")}

        # ── wyr ────────────────────────────────────────────────────────
        dw = _default_wyr()
        if is_gen3:
            stored = data["wyr"]
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
            }
            wyr["enabled"] = stored["enabled"] if "enabled" in stored else bool(wyr.get("channel_id"))
        elif is_gen2:
            wyr = {
                "channel_id": channels_g2.get("wyr"),
                "ping_role_id": roles_g2.get("wyr_ping"),
                "post_hour": data.get("wyr_post_hour", dw["post_hour"]),
                "post_minute": data.get("wyr_post_minute", dw["post_minute"]),
                "timezone": data.get("wyr_timezone", dw["timezone"]),
                "default_category": data.get("wyr_default_category", dw["default_category"]),
                "thread_name_format": data.get("wyr_thread_name_format", dw["thread_name_format"]),
                "thread_starter_message": data.get("wyr_thread_starter_message", dw["thread_starter_message"]),
                "thread_auto_archive": data.get("wyr_thread_auto_archive", dw["thread_auto_archive"]),
                "mapping_cleanup_days": data.get("wyr_mapping_cleanup_days", dw["mapping_cleanup_days"]),
            }
            wyr["enabled"] = bool(wyr.get("channel_id"))
        else:
            wyr = {
                "channel_id": data.get("wyr_channel_id"),
                "ping_role_id": data.get("wyr_ping_role_id"),
                "post_hour": data.get("wyr_post_hour", dw["post_hour"]),
                "post_minute": data.get("wyr_post_minute", dw["post_minute"]),
                "timezone": data.get("wyr_timezone", dw["timezone"]),
                "default_category": data.get("wyr_default_category", dw["default_category"]),
                "thread_name_format": data.get("wyr_thread_name_format", dw["thread_name_format"]),
                "thread_starter_message": data.get("wyr_thread_starter_message", dw["thread_starter_message"]),
                "thread_auto_archive": data.get("wyr_thread_auto_archive", dw["thread_auto_archive"]),
                "mapping_cleanup_days": data.get("wyr_mapping_cleanup_days", dw["mapping_cleanup_days"]),
            }
            wyr["enabled"] = bool(wyr.get("channel_id"))

        # ── new_members ────────────────────────────────────────────────
        if "new_members" in data and isinstance(data["new_members"], dict):
            stored = data["new_members"]
            if "welcome_channel_id" in stored:
                # gen3 — all data self-contained
                nm_welcome_ch = stored.get("welcome_channel_id")
                nm_whitelist_role = stored.get("whitelist_role_id")
            else:
                # gen2 — channel/role in outer channels/roles dicts
                nm_welcome_ch = channels_g2.get("welcome")
                nm_whitelist_role = roles_g2.get("whitelist")
            _nm_enabled = (
                stored["enabled"] if "enabled" in stored
                else bool(nm_welcome_ch or nm_whitelist_role)
            )
            new_members = {
                "enabled": _nm_enabled,
                "account_age_requirement_days": stored.get("account_age_requirement_days", 90),
                "auto_kick": stored.get("auto_kick", True),
                "welcome_channel_id": nm_welcome_ch,
                "whitelist_role_id": nm_whitelist_role,
                "whitelist_enabled": stored.get("whitelist_enabled", True),
                "whitelist_role_name": stored.get("whitelist_role_name", "Whitelisted New Member"),
                "welcome_message_enabled": stored.get("welcome_message_enabled", True),
                "welcome_components": stored.get("welcome_components"),
            }
        elif is_gen2:
            new_members = {
                "enabled": bool(channels_g2.get("welcome") or roles_g2.get("whitelist")),
                "account_age_requirement_days": 90,
                "auto_kick": True,
                "welcome_channel_id": channels_g2.get("welcome"),
                "whitelist_role_id": roles_g2.get("whitelist"),
                "whitelist_enabled": True,
                "whitelist_role_name": "Whitelisted New Member",
                "welcome_message_enabled": True,
                "welcome_components": None,
            }
        else:
            _wc = data.get("welcome_channel_id")
            _wr = data.get("whitelist_role_id")
            new_members = {
                "enabled": bool(data.get("new_members_enabled") if "new_members_enabled" in data else (_wc or _wr)),
                "account_age_requirement_days": data.get("account_age_requirement_days", 90),
                "auto_kick": data.get("auto_kick_new_accounts", True),
                "welcome_channel_id": _wc,
                "whitelist_role_id": _wr,
                "whitelist_enabled": data.get("whitelist_enabled", True),
                "whitelist_role_name": data.get("whitelist_role_name", "Whitelisted New Member"),
                "welcome_message_enabled": data.get("welcome_message_enabled", True),
                "welcome_components": data.get("welcome_components"),
            }

        # ── announcement ───────────────────────────────────────────────
        if "announcement" in data and isinstance(data["announcement"], dict):
            stored = data["announcement"]
            if "channel_id" in stored:
                ann_channel = stored.get("channel_id")
            elif is_gen2:
                ann_channel = channels_g2.get("announcement")
            else:
                ann_channel = data.get("announcement_channel_id")
            ann = {
                "channel_id": ann_channel,
                "thread_auto_create": stored.get("thread_auto_create", True),
                "thread_name_format": stored.get("thread_name_format", "💬 {message_content}"),
                "thread_auto_archive_duration": stored.get("thread_auto_archive_duration", 1440),
                "thread_welcome_message": stored.get("thread_welcome_message", "💬 **Discussion Thread**\n\nDiscuss this announcement here!"),
                "auto_delete_threads": stored.get("auto_delete_threads", True),
            }
        elif is_gen2:
            ann = {
                "channel_id": channels_g2.get("announcement"),
                "thread_auto_create": True,
                "thread_name_format": "💬 {message_content}",
                "thread_auto_archive_duration": 1440,
                "thread_welcome_message": "💬 **Discussion Thread**\n\nDiscuss this announcement here!",
                "auto_delete_threads": True,
            }
        else:
            ann = {
                "channel_id": data.get("announcement_channel_id"),
                "thread_auto_create": data.get("thread_auto_create", True),
                "thread_name_format": data.get("thread_name_format", "💬 {message_content}"),
                "thread_auto_archive_duration": data.get("thread_auto_archive_duration", 1440),
                "thread_welcome_message": data.get("thread_welcome_message", "💬 **Discussion Thread**\n\nDiscuss this announcement here!"),
                "auto_delete_threads": data.get("auto_delete_threads", True),
            }

        # ── tag_tracker ────────────────────────────────────────────────
        if "tag_tracker" in data and isinstance(data["tag_tracker"], dict):
            stored = data["tag_tracker"]
            if "role_id" in stored:
                tt_role = stored.get("role_id")
            elif is_gen2:
                tt_role = roles_g2.get("tag_tracker")
            else:
                tt_role = data.get("tag_tracker_role_id")
            tag_tracker = {
                "enabled": stored.get("enabled", False),
                "server_tag": stored.get("server_tag"),
                "role_id": tt_role,
            }
        elif is_gen2:
            tag_tracker = {
                "enabled": False,
                "server_tag": None,
                "role_id": roles_g2.get("tag_tracker"),
            }
        else:
            tag_tracker = {
                "enabled": data.get("tag_tracker_enabled", False),
                "server_tag": data.get("tag_tracker_server_tag"),
                "role_id": data.get("tag_tracker_role_id"),
            }

        # ── drops ──────────────────────────────────────────────────────
        _drops_defaults = _default_drops()
        if "drops" in data and isinstance(data["drops"], dict):
            stored = data["drops"]
            if "channel_id" in stored:
                drops_channel = stored.get("channel_id")
            elif is_gen2:
                drops_channel = channels_g2.get("drops")
            else:
                drops_channel = data.get("drops_channel_id")
            drops = {
                "channel_id": drops_channel,
                "tracker_channels": stored.get("tracker_channels", {"Updates": None, "Free": None, "Prime": None}),
                "manager_role_id": stored.get("manager_role_id"),
                "post_hour": stored.get("post_hour", _drops_defaults["post_hour"]),
                "post_minute": stored.get("post_minute", _drops_defaults["post_minute"]),
                "timezone": stored.get("timezone", _drops_defaults["timezone"]),
            }
            if "enabled" in stored:
                drops["enabled"] = stored["enabled"]
            else:
                _any_ch = drops.get("channel_id") or any(drops["tracker_channels"].values())
                drops["enabled"] = bool(_any_ch)
        elif is_gen2:
            drops = {
                "channel_id": channels_g2.get("drops"),
                "tracker_channels": data.get("drops_tracker_channels", {"Updates": None, "Free": None, "Prime": None}),
                "manager_role_id": None,
                "post_hour": _drops_defaults["post_hour"],
                "post_minute": _drops_defaults["post_minute"],
                "timezone": _drops_defaults["timezone"],
            }
            _any_ch = drops.get("channel_id") or any(drops["tracker_channels"].values())
            drops["enabled"] = bool(_any_ch)
        else:
            drops = {
                "channel_id": data.get("drops_channel_id"),
                "tracker_channels": {"Updates": None, "Free": None, "Prime": None},
                "manager_role_id": None,
                "post_hour": _drops_defaults["post_hour"],
                "post_minute": _drops_defaults["post_minute"],
                "timezone": _drops_defaults["timezone"],
            }
            drops["enabled"] = bool(drops.get("channel_id"))

        # ── suggestions ────────────────────────────────────────────────
        if "suggestions" in data and isinstance(data["suggestions"], dict):
            suggestions = {"channel_id": data["suggestions"].get("channel_id")}
        elif is_gen2:
            suggestions = {"channel_id": channels_g2.get("suggestions")}
        else:
            suggestions = {"channel_id": data.get("suggestions_channel_id")}

        # ── boost ──────────────────────────────────────────────────────
        if "boost" in data and isinstance(data["boost"], dict):
            _bstored = data["boost"]
            boost = {"channel_id": _bstored.get("channel_id")}
            boost["enabled"] = _bstored["enabled"] if "enabled" in _bstored else bool(boost.get("channel_id"))
        elif is_gen2:
            boost = {"channel_id": channels_g2.get("boost_log")}
            boost["enabled"] = bool(boost.get("channel_id"))
        else:
            boost = {"channel_id": data.get("boost_log_channel_id")}
            boost["enabled"] = bool(boost.get("channel_id"))

        # ── guide ──────────────────────────────────────────────────────
        dg = _default_guide()
        if "guide" in data and isinstance(data["guide"], dict):
            stored = data["guide"]
            guide = {
                "enabled": stored.get("enabled", dg["enabled"]),
                "channel_id": stored.get("channel_id", dg["channel_id"]),
            }
        else:
            guide = dict(dg)

        # ── embed ──────────────────────────────────────────────────────
        legacy_role_tier = data.get("embed_role_tier_mapping", {})
        if "embed" in data and isinstance(data["embed"], dict):
            stored = data["embed"]
            if "description_limits" in stored or "color_tiers" in stored or "feature_access" in stored:
                # gen3 — all embed settings inside the embed dict
                embed = {
                    "default_color": stored.get("default_color"),
                    "role_tier": stored.get("role_tier", legacy_role_tier),
                    "description_limits": stored.get("description_limits", {"default_limit": 500, "limits": {}}),
                    "color_tiers": stored.get("color_tiers", {}),
                    "feature_access": stored.get("feature_access", {}),
                }
                embed["enabled"] = stored["enabled"] if "enabled" in stored else bool(embed.get("role_tier"))
            else:
                # gen2 — embed dict exists but flat settings are at top level
                embed = {
                    "default_color": stored.get("default_color"),
                    "role_tier": stored.get("role_tier", legacy_role_tier),
                    "description_limits": data.get("embed_description_limits", {"default_limit": 500, "limits": {}}),
                    "color_tiers": data.get("embed_color_tiers", {}),
                    "feature_access": data.get("embed_feature_access", {}),
                }
                embed["enabled"] = stored["enabled"] if "enabled" in stored else bool(embed.get("role_tier"))
        else:
            embed = {
                "default_color": data.get("default_embed_color"),
                "role_tier": legacy_role_tier,
                "description_limits": data.get("embed_description_limits", {"default_limit": 500, "limits": {}}),
                "color_tiers": data.get("embed_color_tiers", {}),
                "feature_access": data.get("embed_feature_access", {}),
            }
            embed["enabled"] = bool(embed.get("role_tier"))

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
                async with self._cache_lock:
                    self._settings_cache[guild_id] = {
                        k: v for k, v in doc.items() if k not in _STRUCTURED_KEYS
                    }
                logger.debug(f"Loaded config from database for guild {guild_id}")
            else:
                config = GuildConfig(guild_id=guild_id)
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
        """Save a guild's structured configuration to the database.

        On first save of a legacy document, removes old channels dict and
        flat WYR/embed settings via $unset so the document is clean.
        """
        if not self._initialized:
            await self.initialize()

        try:
            now = datetime.now(timezone.utc)
            existing = await self._collection.find_one({"guild_id": config.guild_id})

            if existing:
                config.updated_at = now
                update_op: Dict[str, Any] = {"$set": config.to_dict()}
                # Migrate: remove legacy fields if they still exist
                fields_to_unset = {f: "" for f in _LEGACY_FIELDS if f in existing}
                if fields_to_unset:
                    update_op["$unset"] = fields_to_unset
                await self._collection.update_one(
                    {"guild_id": config.guild_id},
                    update_op,
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

    async def get_setting(self, key: str, guild_id: int, default: Any = None) -> Any:
        """Get a per-guild flat setting."""
        if not self._initialized:
            await self.initialize()
        if guild_id not in self._settings_cache:
            await self._load_settings_cache(guild_id)
        return self._settings_cache[guild_id].get(key, DEFAULT_SETTINGS.get(key, default))

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
                self._settings_cache.setdefault(guild_id, {})[key] = value
            return True
        except Exception as e:
            logger.error(f"Error setting '{key}' for guild {guild_id}: {e}", exc_info=True)
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
                self._settings_cache.setdefault(guild_id, {}).update(settings)
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


# ── Backward-compat shims ─────────────────────────────────────────────────────

async def get_config_manager() -> GuildConfigManager:
    """Backward-compat alias for get_guild_config_manager()."""
    return await get_guild_config_manager()


def get_config_manager_sync() -> Optional[GuildConfigManager]:
    """Get the global GuildConfigManager instance synchronously (may be None)."""
    return _guild_config_manager


def set_config_manager(manager: GuildConfigManager) -> None:
    """Set the global GuildConfigManager instance (backward compat)."""
    global _guild_config_manager
    _guild_config_manager = manager


# ConfigManager is aliased to GuildConfigManager for any remaining import sites.
ConfigManager = GuildConfigManager
