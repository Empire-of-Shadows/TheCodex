"""
Suggestion Actions - Business logic for Suggestion configuration via admin panel.

All read/write goes through storage.config_manager (GuildConfigManager).
Suggestion settings live inside config.suggestions on the GuildConfig dataclass.
"""

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import discord

from utils.logger import get_logger
from storage.config_manager import get_config, get_guild_config_manager
from storage.database_manager import db_manager

logger = get_logger("SuggestionActions")

# Valid statuses for admin updates
VALID_STATUSES = ["Under Review", "Approved", "Implemented", "Rejected", "On Hold"]

# Embed colours keyed by status string
_STATUS_COLORS = {
    "Pending": discord.Color.blue(),
    "Under Review": discord.Color.orange(),
    "Approved": discord.Color.green(),
    "Implemented": discord.Color.gold(),
    "Rejected": discord.Color.red(),
    "On Hold": discord.Color.purple(),
}


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
    async def get_overview(guild_id: int, bot: Optional[discord.Client] = None) -> Dict[str, Any]:
        """Get suggestion config and stats for the status view.

        When *bot* is provided the overview includes category_distribution and
        top_contributors with resolved display names.
        """
        config = await get_config(guild_id)
        channel_id = config.suggestions.get("channel_id")

        total_suggestions = 0
        status_breakdown: Dict[str, int] = {}
        category_breakdown: Dict[str, int] = {}
        top_contributors: list[Dict[str, Any]] = []
        total_votes = 0

        try:
            suggestions_cm = db_manager.get_collection_manager("suggestions_suggestions")
            col = await suggestions_cm.get_collection()

            total_suggestions = await col.count_documents({"guild_id": guild_id})

            # Status distribution
            async for doc in await col.aggregate([
                {"$match": {"guild_id": guild_id}},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]):
                status_breakdown[doc["_id"]] = doc["count"]

            # Category distribution
            async for doc in await col.aggregate([
                {"$match": {"guild_id": guild_id}},
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            ]):
                category_breakdown[doc["_id"]] = doc["count"]

            # Top contributors (up to 5, non-anonymous)
            contributor_docs: list = []
            async for doc in await col.aggregate([
                {"$match": {"guild_id": guild_id, "anonymous": False}},
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5},
            ]):
                contributor_docs.append(doc)

            for doc in contributor_docs:
                user_id = doc["_id"]
                display = f"User {user_id}"
                if bot:
                    user = bot.get_user(user_id)
                    if user:
                        display = user.display_name
                top_contributors.append({"display_name": display, "count": doc["count"]})

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
            "category_breakdown": category_breakdown,
            "top_contributors": top_contributors,
            "total_votes": total_votes,
        }

    # -- Update Status ------------------------------------------------------

    @staticmethod
    async def update_suggestion_status(
        guild_id: int,
        suggestion_id_prefix: str,
        status: str,
        admin_id: int,
        reason: str,
        bot: discord.Client,
    ) -> Dict[str, Any]:
        """Resolve a suggestion by ID prefix, update its status, embed, and thread.

        Returns ``{"success": bool, "message": str}``.
        """
        try:
            suggestions_cm = db_manager.get_collection_manager("suggestions_suggestions")
            col = await suggestions_cm.get_collection()

            # Find the suggestion by prefix within this guild
            cursor = col.find({"guild_id": guild_id})
            full_id: Optional[str] = None
            async for doc in cursor:
                if doc["suggestion_id"].startswith(suggestion_id_prefix):
                    full_id = doc["suggestion_id"]
                    break

            if not full_id:
                return {"success": False, "message": f"No suggestion found starting with `{suggestion_id_prefix}`."}

            # Update in DB
            update_doc: Dict[str, Any] = {"status": status, "last_updated_by": admin_id}
            if reason:
                update_doc["status_reason"] = reason
            await col.update_one({"suggestion_id": full_id}, {"$set": update_doc})

            # Queue notification for non-anonymous suggestions
            suggestion = await col.find_one({"suggestion_id": full_id})
            if suggestion and not suggestion.get("anonymous") and suggestion.get("user_id"):
                try:
                    notif_cm = db_manager.get_collection_manager("suggestions_notification_queue")
                    notif_col = await notif_cm.get_collection()
                    await notif_col.insert_one({
                        "user_id": suggestion["user_id"],
                        "suggestion_id": full_id,
                        "type": "status_update",
                        "status": status,
                        "reason": reason,
                        "sent": False,
                    })
                except Exception as notif_err:
                    logger.warning("Failed to queue notification: %s", notif_err)

            # Update the suggestion embed in the channel
            if suggestion and suggestion.get("message_id"):
                try:
                    sug_guild_id = suggestion.get("guild_id") or guild_id
                    sug_config = await get_config(sug_guild_id)
                    channel = bot.get_channel(sug_config.suggestions["channel_id"])
                    if channel:
                        message = await channel.fetch_message(suggestion["message_id"])
                        if message and message.embeds:
                            embed = message.embeds[0]
                            # Update Status field
                            for i, field in enumerate(embed.fields):
                                if field.name == "Status":
                                    embed.set_field_at(i, name="Status", value=status, inline=True)
                                    break
                            else:
                                embed.add_field(name="Status", value=status, inline=True)
                            embed.color = _STATUS_COLORS.get(status, discord.Color.blue())
                            await message.edit(embed=embed)
                except Exception as edit_err:
                    logger.error("Failed to update suggestion embed for %s: %s", full_id, edit_err, exc_info=True)

                # Rename thread
                if suggestion.get("thread_id"):
                    try:
                        thread = bot.get_channel(suggestion["thread_id"])
                        if thread and hasattr(thread, "edit"):
                            await thread.edit(name=f"[{status}] {thread.name}")
                    except Exception as thread_err:
                        logger.warning("Could not rename thread %s: %s", suggestion["thread_id"], thread_err)

            logger.info("Admin %s updated suggestion %s to %s", admin_id, suggestion_id_prefix, status)
            return {"success": True, "message": f"Updated suggestion `{suggestion_id_prefix}` to **{status}**."}

        except Exception as e:
            logger.error("Error updating suggestion status: %s", e, exc_info=True)
            return {"success": False, "message": "An error occurred while updating the suggestion."}

    # -- Export -------------------------------------------------------------

    @staticmethod
    async def export_suggestions(
        guild_id: int,
        format_type: str,
    ) -> Optional[Tuple[discord.File, int]]:
        """Export all suggestions for a guild as CSV or JSON.

        Returns ``(discord.File, count)`` or ``None`` if there are no suggestions.
        """
        try:
            suggestions_cm = db_manager.get_collection_manager("suggestions_suggestions")
            col = await suggestions_cm.get_collection()
            suggestions = await col.find({"guild_id": guild_id}).to_list(length=1000)

            if not suggestions:
                return None

            if format_type == "CSV":
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow([
                    "ID", "User ID", "Text", "Category", "Status", "Anonymous",
                    "Created At", "Updated At",
                ])
                for s in suggestions:
                    writer.writerow([
                        s.get("suggestion_id", ""),
                        s.get("user_id", ""),
                        s.get("text", ""),
                        s.get("category", ""),
                        s.get("status", ""),
                        s.get("anonymous", False),
                        s.get("created_at", ""),
                        s.get("updated_at", ""),
                    ])
                file_content = output.getvalue().encode("utf-8")
                file = discord.File(io.BytesIO(file_content), filename="suggestions.csv")
            else:
                json_data = []
                for s in suggestions:
                    copy = s.copy()
                    copy.pop("_id", None)
                    for key, value in copy.items():
                        if isinstance(value, datetime):
                            copy[key] = value.isoformat()
                    json_data.append(copy)
                json_content = json.dumps(json_data, indent=2).encode("utf-8")
                file = discord.File(io.BytesIO(json_content), filename="suggestions.json")

            return file, len(suggestions)

        except Exception as e:
            logger.error("Error exporting suggestions: %s", e, exc_info=True)
            return None
