"""FROZEN copy of the pre-refactor GuildConfig schema logic (pre-086d39c).

Used ONLY by the m1 migration to convert legacy (Gen1/Gen2) documents to the
current nested schema exactly as the old code did on read+save. Kept self-contained
and frozen so the migration stays reproducible; do not wire this into the live bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional



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
# GuildConfig dataclass - structured per-guild settings
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
                # gen3 - all data self-contained
                nm_welcome_ch = stored.get("welcome_channel_id")
                nm_whitelist_role = stored.get("whitelist_role_id")
            else:
                # gen2 - channel/role in outer channels/roles dicts
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
                # gen3 - all embed settings inside the embed dict
                embed = {
                    "default_color": stored.get("default_color"),
                    "role_tier": stored.get("role_tier", legacy_role_tier),
                    "description_limits": stored.get("description_limits", {"default_limit": 500, "limits": {}}),
                    "color_tiers": stored.get("color_tiers", {}),
                    "feature_access": stored.get("feature_access", {}),
                }
                embed["enabled"] = stored["enabled"] if "enabled" in stored else bool(embed.get("role_tier"))
            else:
                # gen2 - embed dict exists but flat settings are at top level
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
# GuildConfigManager - unified structured + flat settings
# ─────────────────────────────────────────────────────────────────────────────
