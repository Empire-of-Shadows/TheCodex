"""
Drops Actions - Business logic for Updates & Drops configuration via admin panel.

Reads/writes channel config through storage.config_manager.py.
Stats queries go directly to the updates_* collections.
"""

from typing import Any, Dict

import discord

from storage.log import get_logger
from storage.config_manager import get_config, get_guild_config_manager

logger = get_logger("DropsActions")

TRACKER_CATEGORIES = ("Updates", "Free", "Prime")

_SCHEDULE_DEFAULTS = {
    "post_hour": 6,
    "post_minute": 30,
    "timezone": "America/Chicago",
}


class DropsActions:
    """Static async methods for managing drops configuration."""

    # -- Read ---------------------------------------------------------------

    @staticmethod
    async def get_drops_settings(guild_id: int) -> Dict[str, Any]:
        """Get drops channel + tracker channels from guild config."""
        config = await get_config(guild_id)
        return {
            "drops_channel_id": config.drops["channel_id"],
            "drops_tracker_channels": config.drops["tracker_channels"],
            "drops_enabled": config.drops.get("enabled", False),
        }

    # -- Setters ------------------------------------------------------------

    @staticmethod
    async def set_drops_channel(guild_id: int, channel_id: int) -> bool:
        """Set the drops posting channel."""
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, "drops", channel_id)

    @staticmethod
    async def set_tracker_channel(guild_id: int, category: str, channel_id: int) -> bool:
        """Set a tracked channel for a specific category (Updates/Free/Prime)."""
        if category not in TRACKER_CATEGORIES:
            logger.warning(f"Invalid tracker category: {category}")
            return False
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.drops["tracker_channels"][category] = channel_id
        return await manager.save_config(config)

    @staticmethod
    async def remove_tracker_channel(guild_id: int, category: str) -> bool:
        """Clear a tracked channel for a specific category."""
        if category not in TRACKER_CATEGORIES:
            logger.warning(f"Invalid tracker category: {category}")
            return False
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.drops["tracker_channels"][category] = None
        return await manager.save_config(config)

    # -- Stats --------------------------------------------------------------

    @staticmethod
    async def get_drops_stats(guild_id: int) -> Dict[str, Any]:
        """Query updates_totals for guild-specific stats."""
        try:
            from storage.manager import db_manager
            totals_col = db_manager.get_collection_manager('updates_totals')

            stats = {}
            for category in TRACKER_CATEGORIES:
                doc = await totals_col.find_one(
                    {"_id": {"coll": category, "guild_id": guild_id}},
                    projection={"total_count": 1, "average_per_month": 1, "months_with_data": 1}
                )
                if doc:
                    stats[category] = {
                        "total_count": doc.get("total_count", 0),
                        "average_per_month": doc.get("average_per_month", 0.0),
                        "months_with_data": doc.get("months_with_data", 0),
                    }
                else:
                    stats[category] = {"total_count": 0, "average_per_month": 0.0, "months_with_data": 0}
            return stats
        except Exception as e:
            logger.error(f"Error getting drops stats: {e}", exc_info=True)
            return {cat: {"total_count": 0, "average_per_month": 0.0, "months_with_data": 0} for cat in TRACKER_CATEGORIES}

    # -- Overview -----------------------------------------------------------

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get combined settings + stats for status view."""
        settings = await DropsActions.get_drops_settings(guild_id)
        stats = await DropsActions.get_drops_stats(guild_id)
        schedule = await DropsActions.get_schedule(guild_id)
        return {
            **settings,
            "stats": stats,
            "schedule": schedule,
        }

    # -- Manager Role -------------------------------------------------------

    @staticmethod
    async def get_manager_role(guild_id: int) -> int | None:
        """Get the drops manager role ID for a guild."""
        config = await get_config(guild_id)
        return config.drops.get("manager_role_id")

    @staticmethod
    async def set_manager_role(guild_id: int, role_id: int) -> bool:
        """Set the drops manager role ID for a guild."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.drops["manager_role_id"] = role_id
        return await manager.save_config(config)

    @staticmethod
    async def has_drops_management(member: discord.Member) -> bool:
        """Check if a member has drops management access.

        Returns True if the member has the configured manager_role_id,
        any admin role, or the administrator permission.
        """
        if member.guild_permissions.administrator:
            return True

        config = await get_config(member.guild.id)

        user_role_ids = {role.id for role in member.roles}

        # Check admin roles
        if user_role_ids & set(config.roles["admin_role_ids"]):
            return True

        # Check drops manager role
        manager_role_id = config.drops.get("manager_role_id")
        if manager_role_id and manager_role_id in user_role_ids:
            return True

        return False

    # -- Enabled toggle -----------------------------------------------------

    @staticmethod
    async def get_enabled(guild_id: int) -> bool:
        """Get whether Updates & Drops is enabled for a guild."""
        config = await get_config(guild_id)
        return config.drops.get("enabled", False)

    @staticmethod
    async def set_enabled(guild_id: int, enabled: bool) -> bool:
        """Enable or disable Updates & Drops for a guild."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.drops["enabled"] = enabled
        return await manager.save_config(config)

    # -- Schedule -----------------------------------------------------------

    @staticmethod
    async def get_schedule(guild_id: int) -> Dict[str, Any]:
        """Get drops post schedule (hour, minute, timezone) for a guild."""
        config = await get_config(guild_id)
        return {
            "hour": config.drops.get("post_hour", _SCHEDULE_DEFAULTS["post_hour"]),
            "minute": config.drops.get("post_minute", _SCHEDULE_DEFAULTS["post_minute"]),
            "timezone": config.drops.get("timezone", _SCHEDULE_DEFAULTS["timezone"]),
        }

    @staticmethod
    async def set_schedule(guild_id: int, hour: int, minute: int, tz_name: str) -> bool:
        """Set the drops post schedule for a guild."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.drops["post_hour"] = hour
        config.drops["post_minute"] = minute
        config.drops["timezone"] = tz_name
        return await manager.save_config(config)

    @staticmethod
    async def get_schedule_hour(guild_id: int) -> list:
        return [str((await DropsActions.get_schedule(guild_id))["hour"])]

    @staticmethod
    async def set_schedule_hour(guild_id: int, values: list) -> bool:
        s = await DropsActions.get_schedule(guild_id)
        return await DropsActions.set_schedule(guild_id, int(values[0]), s["minute"], s["timezone"])

    @staticmethod
    async def get_schedule_minute(guild_id: int) -> list:
        return [str((await DropsActions.get_schedule(guild_id))["minute"])]

    @staticmethod
    async def set_schedule_minute(guild_id: int, values: list) -> bool:
        s = await DropsActions.get_schedule(guild_id)
        return await DropsActions.set_schedule(guild_id, s["hour"], int(values[0]), s["timezone"])

    @staticmethod
    async def get_schedule_timezone(guild_id: int) -> list:
        return [(await DropsActions.get_schedule(guild_id))["timezone"]]

    @staticmethod
    async def set_schedule_timezone(guild_id: int, values: list) -> bool:
        s = await DropsActions.get_schedule(guild_id)
        return await DropsActions.set_schedule(guild_id, s["hour"], s["minute"], values[0])
