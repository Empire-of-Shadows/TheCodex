"""
Suggestion Actions - Business logic for Suggestion configuration via admin panel.

All read/write goes through storage.config_manager (GuildConfigManager).
Suggestion settings live inside config.suggestions on the GuildConfig dataclass.
"""

from typing import Any, Dict

from utils.logger import get_logger
from storage.config_manager import get_config, get_guild_config_manager
from storage.database_manager import db_manager

logger = get_logger("SuggestionActions")


class SuggestionActions:
    """Static async methods for managing suggestion configuration."""

    # -- Channel ------------------------------------------------------------

    @staticmethod
    async def get_suggestion_channel_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        ch = config.suggestions.get("channel_id")
        return [str(ch)] if ch else []

    @staticmethod
    async def set_suggestion_channel(guild_id: int, channel_id: int) -> bool:
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, 'suggestions', channel_id)

    @staticmethod
    async def clear_suggestion_channel(guild_id: int) -> bool:
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, 'suggestions', None)

    # -- Overview -----------------------------------------------------------

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get suggestion config and stats for the status view."""
        config = await get_config(guild_id)
        channel_id = config.suggestions.get("channel_id")

        # Collect stats from DB
        total_suggestions = 0
        status_breakdown = {}
        total_votes = 0

        try:
            suggestions_cm = db_manager.get_collection_manager("suggestions_suggestions")
            col = await suggestions_cm.get_collection()

            total_suggestions = await col.count_documents({"guild_id": guild_id})

            pipeline = [
                {"$match": {"guild_id": guild_id}},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]
            async for doc in col.aggregate(pipeline):
                status_breakdown[doc["_id"]] = doc["count"]
        except Exception as e:
            logger.warning("Failed to query suggestions collection: %s", e)

        try:
            votes_cm = db_manager.get_collection_manager("suggestions_votes")
            votes_col = await votes_cm.get_collection()
            total_votes = await votes_col.count_documents({"guild_id": guild_id})
        except Exception as e:
            logger.warning("Failed to query votes collection: %s", e)

        return {
            "channel_id": channel_id,
            "total_suggestions": total_suggestions,
            "status_breakdown": status_breakdown,
            "total_votes": total_votes,
        }
