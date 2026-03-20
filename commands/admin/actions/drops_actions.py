"""
Drops Actions - Business logic for Updates & Drops configuration via admin panel.

Reads/writes channel config through storage.config_manager.py.
Stats queries go directly to the updates_* collections.
"""

from typing import Any, Dict

from utils.logger import get_logger
from storage.config_manager import get_config, get_guild_config_manager

logger = get_logger("DropsActions")

TRACKER_CATEGORIES = ("Updates", "Free", "Prime")


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
            from storage.database_manager import db_manager
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
        return {
            **settings,
            "stats": stats,
        }

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
