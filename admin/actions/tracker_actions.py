"""
Tracker Actions - Business logic for Boost Tracker and Tag Tracker configuration via admin panel.

All read/write goes through storage.config_manager.py.
"""

from typing import Any, Dict, List

from storage.log import get_logger
from storage.settings.config_manager import get_config, get_guild_config_manager

logger = get_logger("TrackerActions")


class TrackerActions:
    """Static async methods for managing tracker configuration."""

    # -- Tag Tracker Read ---------------------------------------------------

    @staticmethod
    async def get_tag_tracker_settings(guild_id: int) -> Dict[str, Any]:
        """Get tag tracker settings from guild config."""
        config = await get_config(guild_id)
        return {
            "tag_tracker_enabled": config.tag_tracker["enabled"],
            "tag_tracker_role_id": config.tag_tracker["role_id"],
            "tag_tracker_server_tag": config.tag_tracker["server_tag"],
        }

    # -- Tag Tracker Setters ------------------------------------------------

    @staticmethod
    async def set_tag_tracker_enabled(guild_id: int, enabled: bool) -> bool:
        """Toggle tag tracker on/off."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.tag_tracker["enabled"] = enabled
        return await manager.save_config(config)

    @staticmethod
    async def set_tag_tracker_role(guild_id: int, role_id: int) -> bool:
        """Set the role to assign when a member has the server tag."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.tag_tracker["role_id"] = role_id
        return await manager.save_config(config)

    @staticmethod
    async def set_tag_tracker_server_tag(guild_id: int, tag: str) -> bool:
        """Store the server tag text the bot detected (display only - matching is
        by server id, see Features/trackers/tag/tag_tracker.py)."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.tag_tracker["server_tag"] = tag
        return await manager.save_config(config)

    @staticmethod
    def server_tags_available(guild) -> bool:
        """Whether Discord lets this server have a tag (the GUILD_TAGS boost perk)."""
        from Features.trackers.tag.tag_tracker import GUILD_TAGS_FEATURE

        return GUILD_TAGS_FEATURE in (getattr(guild, "features", None) or [])

    @staticmethod
    def detect_server_tag(guild) -> tuple[str | None, int]:
        """(tag text, members wearing it) read from the bot's member cache.

        Replaced 2026-11-20: the old version read a ``clan`` field from the raw
        server object, which Discord does not send to bots (checked against a live
        pull), so it always answered "no tag". The tag text is only knowable from a
        member wearing it.
        """
        from Features.trackers.tag.tag_tracker import detect_server_tag

        return detect_server_tag(guild)

    # -- Boost Tracker Read -------------------------------------------------

    @staticmethod
    async def get_boost_tracker_settings(guild_id: int) -> Dict[str, Any]:
        """Get boost tracker settings from guild config."""
        config = await get_config(guild_id)
        return {
            "boost_enabled": config.boost.get("enabled", False),
            "boost_log_channel_id": config.boost["channel_id"],
        }

    # -- Boost Tracker Setters ----------------------------------------------

    @staticmethod
    async def set_boost_log_channel(guild_id: int, channel_id: int) -> bool:
        """Set boost log channel via the channel setter."""
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, 'boost_log', channel_id)

    # -- Stats --------------------------------------------------------------

    @staticmethod
    async def get_boost_stats(guild_id: int) -> Dict[str, Any]:
        """Count active boosters and total boost events from DB."""
        try:
            from storage.settings.collections import db_manager
            boosts_col = db_manager.get_collection_manager('serverdata_boosts')
            events_col = db_manager.get_collection_manager('serverdata_boost_events')

            active_boosters = await boosts_col.count_documents({'guild_id': str(guild_id)})
            total_events = await events_col.count_documents({'guild_id': str(guild_id)})

            return {
                "active_boosters": active_boosters,
                "total_events": total_events,
            }
        except Exception as e:
            logger.error(f"Error getting boost stats: {e}", exc_info=True)
            return {"active_boosters": 0, "total_events": 0}

    @staticmethod
    async def get_stored_boosters(guild_id: int) -> List[Dict[str, Any]]:
        """Active boosters as the tracker recorded them, longest-boosting first.

        The collection only ever holds current boosters - the tracker deletes the
        document when a member stops - so every row here is someone boosting now.
        This is the fallback for the panel display when the guild's member cache is
        not populated and ``guild.premium_subscribers`` would read as empty.
        """
        try:
            from storage.settings.collections import db_manager
            boosts_col = db_manager.get_collection_manager('serverdata_boosts')
            return await boosts_col.find_many(
                {'guild_id': str(guild_id)},
                sort=[('boost_start', 1)],
            )
        except Exception as e:
            logger.error(f"Error getting stored boosters: {e}", exc_info=True)
            return []

    @staticmethod
    async def get_recent_boost_events(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """The guild's most recent boost start/stop events, newest first."""
        try:
            from storage.settings.collections import db_manager
            events_col = db_manager.get_collection_manager('serverdata_boost_events')
            return await events_col.find_many(
                {'guild_id': str(guild_id)},
                sort=[('timestamp', -1)],
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting recent boost events: {e}", exc_info=True)
            return []

    # -- Overview -----------------------------------------------------------

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get combined settings + stats for status view."""
        tag_settings = await TrackerActions.get_tag_tracker_settings(guild_id)
        boost_settings = await TrackerActions.get_boost_tracker_settings(guild_id)
        boost_stats = await TrackerActions.get_boost_stats(guild_id)
        return {
            **tag_settings,
            **boost_settings,
            "boost_stats": boost_stats,
        }

    # -- Boost Enabled toggle -----------------------------------------------

    @staticmethod
    async def get_boost_enabled(guild_id: int) -> bool:
        """Get whether Boost Tracker is enabled for a guild."""
        config = await get_config(guild_id)
        return config.boost.get("enabled", False)

    @staticmethod
    async def set_boost_enabled(guild_id: int, enabled: bool) -> bool:
        """Enable or disable Boost Tracker for a guild."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.boost["enabled"] = enabled
        return await manager.save_config(config)
