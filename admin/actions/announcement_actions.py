"""
Announcement Actions - Business logic for Announcement configuration via admin panel.

All read/write goes through storage.config_manager (GuildConfigManager).
Announcement settings live inside config.announcement on the GuildConfig dataclass.
"""

from typing import Any, Dict

from storage.log import get_logger
from storage.settings.config_manager import get_config, get_guild_config_manager

logger = get_logger("AnnouncementActions")


class AnnouncementActions:
    """Static async methods for managing announcement configuration."""

    # -- Channel ------------------------------------------------------------

    @staticmethod
    async def get_announcement_channel_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        ch = config.announcement.get("channel_id")
        return [str(ch)] if ch else []

    @staticmethod
    async def set_announcement_channel(guild_id: int, channel_id: int) -> bool:
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, 'announcement', channel_id)

    @staticmethod
    async def clear_announcement_channel(guild_id: int) -> bool:
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, 'announcement', None)

    # -- Thread Auto-Create -------------------------------------------------

    @staticmethod
    async def get_thread_auto_create_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        return ["true" if config.announcement.get("thread_auto_create", True) else "false"]

    @staticmethod
    async def set_thread_auto_create_from_list(guild_id: int, vals: list) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.announcement["thread_auto_create"] = vals[0] == "true"
        return await manager.save_config(config)

    # -- Thread Name Format -------------------------------------------------

    @staticmethod
    async def get_thread_name_format_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        fmt = config.announcement.get("thread_name_format", "💬 {message_content}")
        return [fmt]

    @staticmethod
    async def set_thread_name_format(guild_id: int, vals: list) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.announcement["thread_name_format"] = vals[0]
        return await manager.save_config(config)

    # -- Thread Auto-Archive Duration ---------------------------------------

    @staticmethod
    async def get_thread_auto_archive_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        duration = config.announcement.get("thread_auto_archive_duration", 1440)
        return [str(duration)]

    @staticmethod
    async def set_thread_auto_archive_from_list(guild_id: int, vals: list) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.announcement["thread_auto_archive_duration"] = int(vals[0])
        return await manager.save_config(config)

    # -- Thread Welcome Message ---------------------------------------------

    @staticmethod
    async def get_thread_welcome_message_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        msg = config.announcement.get(
            "thread_welcome_message",
            "💬 **Discussion Thread**\n\nDiscuss this announcement here!",
        )
        return [msg]

    @staticmethod
    async def set_thread_welcome_message(guild_id: int, vals: list) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.announcement["thread_welcome_message"] = vals[0]
        return await manager.save_config(config)

    # -- Auto-Delete Threads ------------------------------------------------

    @staticmethod
    async def get_auto_delete_threads_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        return ["true" if config.announcement.get("auto_delete_threads", True) else "false"]

    @staticmethod
    async def set_auto_delete_threads_from_list(guild_id: int, vals: list) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.announcement["auto_delete_threads"] = vals[0] == "true"
        return await manager.save_config(config)

    # -- Overview -----------------------------------------------------------

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get all announcement settings for status view."""
        config = await get_config(guild_id)
        ann = config.announcement
        return {
            "channel_id": ann.get("channel_id"),
            "thread_auto_create": ann.get("thread_auto_create", True),
            "thread_name_format": ann.get("thread_name_format", "💬 {message_content}"),
            "thread_auto_archive_duration": ann.get("thread_auto_archive_duration", 1440),
            "thread_welcome_message": ann.get(
                "thread_welcome_message",
                "💬 **Discussion Thread**\n\nDiscuss this announcement here!",
            ),
            "auto_delete_threads": ann.get("auto_delete_threads", True),
        }
