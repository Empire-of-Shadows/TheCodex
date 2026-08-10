"""
WYR Config Actions - Business logic for WYR configuration via admin panel.

All read/write goes through storage.config_manager (GuildConfigManager).
WYR settings now live inside config.wyr on the GuildConfig dataclass.
"""

from typing import Any, Dict, Optional
from storage.log import get_logger

logger = get_logger("WYRConfigActions")

_WYR_DEFAULTS = {
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


async def _get_gcm():
    """Get the global GuildConfigManager instance."""
    from storage.settings.config_manager import get_guild_config_manager
    return await get_guild_config_manager()


async def _question_overview(guild_id: int) -> Optional[Dict[str, Any]]:
    """Question-content summary for the status screen, or None if unavailable.

    Imported lazily and failure-tolerant on purpose: the status screen's
    scheduling half must still render if the question bank cannot be reached.
    """
    try:
        from .wyr_question_actions import WYRQuestionActions
        return await WYRQuestionActions.get_overview(guild_id)
    except Exception:
        logger.debug("WYR status: question overview unavailable", exc_info=True)
        return None


class WYRConfigActions:
    """Static async methods for managing WYR configuration."""

    # -- Channel ---------------------------------------------------------

    @staticmethod
    async def get_wyr_channel(guild_id: int) -> Optional[int]:
        """Get the WYR channel ID for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.wyr.get("channel_id")

    @staticmethod
    async def set_wyr_channel(guild_id: int, channel_id: int) -> bool:
        """Set the WYR channel for a guild."""
        gcm = await _get_gcm()
        return await gcm.set_channel(guild_id, "wyr", channel_id)

    # -- Schedule --------------------------------------------------------

    @staticmethod
    async def get_schedule(guild_id: int) -> Dict[str, Any]:
        """Get WYR schedule settings for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return {
            "hour": config.wyr.get("post_hour", _WYR_DEFAULTS["post_hour"]),
            "minute": config.wyr.get("post_minute", _WYR_DEFAULTS["post_minute"]),
            "timezone": config.wyr.get("timezone", _WYR_DEFAULTS["timezone"]),
        }

    @staticmethod
    async def set_schedule(guild_id: int, hour: int, minute: int, timezone: str) -> bool:
        """Set the WYR post schedule for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["post_hour"] = hour
        config.wyr["post_minute"] = minute
        config.wyr["timezone"] = timezone
        return await gcm.save_config(config)

    # -- Thread Settings -------------------------------------------------

    @staticmethod
    async def get_thread_settings(guild_id: int) -> Dict[str, Any]:
        """Get WYR thread settings for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return {
            "name_format": config.wyr.get("thread_name_format", _WYR_DEFAULTS["thread_name_format"]),
            "starter_message": config.wyr.get("thread_starter_message", _WYR_DEFAULTS["thread_starter_message"]),
            "auto_archive": config.wyr.get("thread_auto_archive", _WYR_DEFAULTS["thread_auto_archive"]),
        }

    @staticmethod
    async def set_thread_settings(
        guild_id: int,
        name_format: str = None,
        starter_message: str = None,
        auto_archive: int = None,
    ) -> bool:
        """Set WYR thread settings for a guild.  Only updates provided values."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        if name_format is not None:
            config.wyr["thread_name_format"] = name_format
        if starter_message is not None:
            config.wyr["thread_starter_message"] = starter_message
        if auto_archive is not None:
            config.wyr["thread_auto_archive"] = auto_archive
        return await gcm.save_config(config)

    # -- Category --------------------------------------------------------

    @staticmethod
    async def get_category(guild_id: int) -> str:
        """Get the default WYR question category for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.wyr.get("default_category", _WYR_DEFAULTS["default_category"])

    @staticmethod
    async def set_category(guild_id: int, category: str) -> bool:
        """Set the default WYR question category for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["default_category"] = category
        return await gcm.save_config(config)

    # -- Cleanup ---------------------------------------------------------

    @staticmethod
    async def get_cleanup_days(guild_id: int) -> int:
        """Get the WYR mapping cleanup age in days."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.wyr.get("mapping_cleanup_days", _WYR_DEFAULTS["mapping_cleanup_days"])

    @staticmethod
    async def set_cleanup_days(guild_id: int, days: int) -> bool:
        """Set the WYR mapping cleanup age in days."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["mapping_cleanup_days"] = days
        return await gcm.save_config(config)

    # -- Ping Role -------------------------------------------------------

    @staticmethod
    async def get_ping_role(guild_id: int) -> list:
        """Return [str(role_id)] or [] for panel engine compatibility."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        rid = config.wyr.get("ping_role_id")
        return [str(rid)] if rid else []

    @staticmethod
    async def set_ping_role(guild_id: int, role_ids: list) -> bool:
        """Set the WYR ping role from a list of role IDs."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["ping_role_id"] = int(role_ids[0]) if role_ids else None
        return await gcm.save_config(config)

    @staticmethod
    async def clear_ping_role(guild_id: int) -> bool:
        """Remove the WYR ping role."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["ping_role_id"] = None
        return await gcm.save_config(config)

    # -- Subscribe prompt ------------------------------------------------

    @staticmethod
    async def get_subscribe_prompt(guild_id: int) -> bool:
        """Whether the ping role is offered to members who interact with a question."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.wyr.get("subscribe_prompt_enabled", True)

    @staticmethod
    async def set_subscribe_prompt(guild_id: int, enabled: bool) -> bool:
        """Enable or disable the in-line ping-role offer."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["subscribe_prompt_enabled"] = enabled
        return await gcm.save_config(config)

    @staticmethod
    async def get_subscribe_prompt_as_list(guild_id: int) -> list:
        """Return ["true"] / ["false"] for panel engine compatibility."""
        return ["true" if await WYRConfigActions.get_subscribe_prompt(guild_id) else "false"]

    @staticmethod
    async def set_subscribe_prompt_from_list(guild_id: int, values: list) -> bool:
        return await WYRConfigActions.set_subscribe_prompt(guild_id, values[0] == "true")

    # -- Channel list helper (panel engine requires list[str]) -----------

    @staticmethod
    async def _get_channel_list(guild_id: int) -> list:
        """Return [str(channel_id)] or [] for panel engine compatibility."""
        cid = await WYRConfigActions.get_wyr_channel(guild_id)
        return [str(cid)] if cid else []

    # -- Individual schedule getters/setters -----------------------------

    @staticmethod
    async def get_schedule_hour(guild_id: int) -> list:
        return [str((await WYRConfigActions.get_schedule(guild_id))["hour"])]

    @staticmethod
    async def set_schedule_hour(guild_id: int, values: list) -> bool:
        s = await WYRConfigActions.get_schedule(guild_id)
        return await WYRConfigActions.set_schedule(guild_id, int(values[0]), s["minute"], s["timezone"])

    @staticmethod
    async def get_schedule_minute(guild_id: int) -> list:
        return [str((await WYRConfigActions.get_schedule(guild_id))["minute"])]

    @staticmethod
    async def set_schedule_minute(guild_id: int, values: list) -> bool:
        s = await WYRConfigActions.get_schedule(guild_id)
        return await WYRConfigActions.set_schedule(guild_id, s["hour"], int(values[0]), s["timezone"])

    @staticmethod
    async def get_schedule_timezone(guild_id: int) -> list:
        return [(await WYRConfigActions.get_schedule(guild_id))["timezone"]]

    @staticmethod
    async def set_schedule_timezone(guild_id: int, values: list) -> bool:
        s = await WYRConfigActions.get_schedule(guild_id)
        return await WYRConfigActions.set_schedule(guild_id, s["hour"], s["minute"], values[0])

    # -- Category list helper --------------------------------------------

    @staticmethod
    async def get_category_as_list(guild_id: int) -> list:
        """Return [category_str] for panel engine compatibility."""
        return [await WYRConfigActions.get_category(guild_id)]

    # -- Combined thread name + message getter/setter (dual_modal_input) -----

    @staticmethod
    async def get_thread_format_and_message(guild_id: int) -> list:
        s = await WYRConfigActions.get_thread_settings(guild_id)
        return [s.get("name_format", ""), s.get("starter_message", "")]

    @staticmethod
    async def set_thread_format_and_message(guild_id: int, values: list) -> bool:
        return await WYRConfigActions.set_thread_settings(
            guild_id,
            name_format=values[0] if values else None,
            starter_message=values[1] if len(values) > 1 else None,
        )

    # -- Individual thread getters/setters --------------------------------

    @staticmethod
    async def get_thread_name_format(guild_id: int) -> list:
        v = (await WYRConfigActions.get_thread_settings(guild_id)).get("name_format", "")
        return [v] if v else []

    @staticmethod
    async def set_thread_name_format(guild_id: int, values: list) -> bool:
        return await WYRConfigActions.set_thread_settings(guild_id, name_format=values[0])

    @staticmethod
    async def get_thread_starter_message(guild_id: int) -> list:
        v = (await WYRConfigActions.get_thread_settings(guild_id)).get("starter_message", "")
        return [v] if v else []

    @staticmethod
    async def set_thread_starter_message(guild_id: int, values: list) -> bool:
        return await WYRConfigActions.set_thread_settings(guild_id, starter_message=values[0])

    @staticmethod
    async def get_thread_auto_archive(guild_id: int) -> list:
        return [str((await WYRConfigActions.get_thread_settings(guild_id)).get("auto_archive", 1440))]

    @staticmethod
    async def set_thread_auto_archive(guild_id: int, values: list) -> bool:
        return await WYRConfigActions.set_thread_settings(guild_id, auto_archive=int(values[0]))

    # -- Cleanup list helper ----------------------------------------------

    @staticmethod
    async def get_cleanup_days_as_list(guild_id: int) -> list:
        """Return [str(days)] for panel engine compatibility."""
        return [str(await WYRConfigActions.get_cleanup_days(guild_id))]

    # -- Overview --------------------------------------------------------

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get a summary of all WYR settings for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        wyr = config.wyr
        return {
            "wyr_channel_id": wyr.get("channel_id"),
            "wyr_ping_role_id": wyr.get("ping_role_id"),
            "hour": wyr.get("post_hour", _WYR_DEFAULTS["post_hour"]),
            "minute": wyr.get("post_minute", _WYR_DEFAULTS["post_minute"]),
            "timezone": wyr.get("timezone", _WYR_DEFAULTS["timezone"]),
            "default_category": wyr.get("default_category", _WYR_DEFAULTS["default_category"]),
            "thread_name_format": wyr.get("thread_name_format", _WYR_DEFAULTS["thread_name_format"]),
            "thread_starter_message": wyr.get("thread_starter_message", _WYR_DEFAULTS["thread_starter_message"]),
            "thread_auto_archive": wyr.get("thread_auto_archive", _WYR_DEFAULTS["thread_auto_archive"]),
            "mapping_cleanup_days": wyr.get("mapping_cleanup_days", _WYR_DEFAULTS["mapping_cleanup_days"]),
            "subscribe_prompt_enabled": wyr.get("subscribe_prompt_enabled", True),
            # Which questions get posted, and what is in this guild's own bank.
            # Nested rather than flattened so the status view can render it as
            # its own block, and so a failure to reach the bank cannot take the
            # scheduling half of the screen down with it.
            "questions": await _question_overview(guild_id),
        }

    # -- Enabled toggle --------------------------------------------------

    @staticmethod
    async def get_enabled(guild_id: int) -> bool:
        """Get whether WYR is enabled for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.wyr.get("enabled", False)

    @staticmethod
    async def set_enabled(guild_id: int, enabled: bool) -> bool:
        """Enable or disable WYR for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["enabled"] = enabled
        return await gcm.save_config(config)

    @staticmethod
    async def set_skip_initial_post(guild_id: int, skip: bool) -> bool:
        """Set the skip_initial_post flag so the first catch-up post is suppressed."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.wyr["skip_initial_post"] = skip
        return await gcm.save_config(config)

    @staticmethod
    async def has_channel_configured(guild_id: int) -> bool:
        """Return True if a WYR channel has been saved for this guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return bool(config.wyr.get("channel_id"))
