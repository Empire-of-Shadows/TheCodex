"""
New Member Actions - Business logic for New Members configuration via admin panel.

All read/write goes through storage.config_manager.py.
"""

import json
from typing import Any, Dict

from storage.logging import get_logger
from storage.config_manager import get_config, get_guild_config_manager

logger = get_logger("NewMemberActions")


class NewMemberActions:
    """Static async methods for managing New Members configuration."""

    # -- Read Settings ---------------------------------------------------

    @staticmethod
    async def get_settings(guild_id: int) -> Dict[str, Any]:
        """Get all NewMembers settings from guild config."""
        config = await get_config(guild_id)
        return {
            "new_members_enabled": config.new_members["enabled"],
            "account_age_requirement_days": config.new_members["account_age_requirement_days"],
            "auto_kick_new_accounts": config.new_members["auto_kick"],
            "welcome_message_enabled": config.new_members["welcome_message_enabled"],
            "whitelist_enabled": config.new_members["whitelist_enabled"],
            "whitelist_role_name": config.new_members["whitelist_role_name"],
            "whitelist_role_id": config.new_members["whitelist_role_id"],
            "welcome_channel_id": config.new_members["welcome_channel_id"],
        }

    # -- Setters ---------------------------------------------------------

    @staticmethod
    async def set_account_age(guild_id: int, days: int) -> bool:
        """Update account age requirement."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["account_age_requirement_days"] = days
        return await manager.save_config(config)

    @staticmethod
    async def set_auto_kick(guild_id: int, enabled: bool) -> bool:
        """Toggle auto-kick for new accounts."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["auto_kick"] = enabled
        return await manager.save_config(config)

    @staticmethod
    async def set_welcome_enabled(guild_id: int, enabled: bool) -> bool:
        """Toggle welcome messages."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["welcome_message_enabled"] = enabled
        return await manager.save_config(config)

    @staticmethod
    async def set_whitelist_enabled(guild_id: int, enabled: bool) -> bool:
        """Toggle whitelist system."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["whitelist_enabled"] = enabled
        return await manager.save_config(config)

    @staticmethod
    async def set_whitelist_role_name(guild_id: int, name: str) -> bool:
        """Set whitelist role name."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["whitelist_role_name"] = name
        return await manager.save_config(config)

    @staticmethod
    async def set_whitelist_role_id(guild_id: int, role_id: int) -> bool:
        """Set whitelist role ID."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["whitelist_role_id"] = role_id
        return await manager.save_config(config)

    @staticmethod
    async def set_welcome_channel(guild_id: int, channel_id: int) -> bool:
        """Set welcome channel ID."""
        manager = await get_guild_config_manager()
        return await manager.set_channel(guild_id, "welcome", channel_id)

    # -- Panel Engine Wrappers -------------------------------------------

    @staticmethod
    async def get_account_age_as_list(guild_id: int) -> list:
        s = await NewMemberActions.get_settings(guild_id)
        return [str(s.get("account_age_requirement_days", 90))]

    @staticmethod
    async def set_account_age_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_account_age(guild_id, int(values[0]))

    @staticmethod
    async def get_auto_kick_as_list(guild_id: int) -> list:
        s = await NewMemberActions.get_settings(guild_id)
        return ["true" if s.get("auto_kick_new_accounts", True) else "false"]

    @staticmethod
    async def set_auto_kick_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_auto_kick(guild_id, values[0] == "true")

    @staticmethod
    async def get_welcome_enabled_as_list(guild_id: int) -> list:
        s = await NewMemberActions.get_settings(guild_id)
        return ["true" if s.get("welcome_message_enabled", True) else "false"]

    @staticmethod
    async def set_welcome_enabled_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_welcome_enabled(guild_id, values[0] == "true")

    @staticmethod
    async def get_whitelist_system_as_list(guild_id: int) -> list:
        s = await NewMemberActions.get_settings(guild_id)
        return ["true" if s.get("whitelist_enabled", True) else "false"]

    @staticmethod
    async def set_whitelist_system_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_whitelist_enabled(guild_id, values[0] == "true")

    @staticmethod
    async def get_welcome_channel_as_list(guild_id: int) -> list:
        s = await NewMemberActions.get_settings(guild_id)
        cid = s.get("welcome_channel_id")
        return [str(cid)] if cid else []

    @staticmethod
    async def set_welcome_channel_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_welcome_channel(guild_id, int(values[0]))

    @staticmethod
    async def clear_welcome_channel(guild_id: int) -> bool:
        return await NewMemberActions.set_welcome_channel(guild_id, None)

    @staticmethod
    async def get_whitelist_role_as_list(guild_id: int) -> list:
        s = await NewMemberActions.get_settings(guild_id)
        rid = s.get("whitelist_role_id")
        return [str(rid)] if rid else []

    @staticmethod
    async def set_whitelist_role_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_whitelist_role_id(guild_id, int(values[0]))

    @staticmethod
    async def clear_whitelist_role(guild_id: int) -> bool:
        return await NewMemberActions.set_whitelist_role_id(guild_id, None)

    @staticmethod
    async def get_welcome_components_raw(guild_id: int) -> list:
        config = await get_config(guild_id)
        val = config.new_members.get("welcome_components")
        return [json.dumps(val, indent=2, ensure_ascii=False)] if val else []

    @staticmethod
    async def set_welcome_components_from_list(guild_id: int, values: list) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        raw = values[0].strip() if values else ""
        config.new_members["welcome_components"] = json.loads(raw) if raw else None
        return await manager.save_config(config)

    @staticmethod
    async def clear_welcome_components(guild_id: int) -> bool:
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["welcome_components"] = None
        return await manager.save_config(config)

    # -- Stats -----------------------------------------------------------

    @staticmethod
    async def get_whitelist_stats(guild_id: int) -> Dict[str, Any]:
        """Count active/total whitelist entries from DB."""
        try:
            from storage.manager import db_manager
            whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')

            all_entries = await whitelist_collection.find_many({'guild_id': guild_id})
            active_entries = [e for e in all_entries if e.get('is_active', True)]
            role_assigned = [e for e in active_entries if e.get('role_assigned', False)]

            return {
                "total": len(all_entries),
                "active": len(active_entries),
                "inactive": len(all_entries) - len(active_entries),
                "role_assigned": len(role_assigned),
            }
        except Exception as e:
            logger.error(f"Error getting whitelist stats: {e}", exc_info=True)
            return {"total": 0, "active": 0, "inactive": 0, "role_assigned": 0}

    # -- Overview --------------------------------------------------------

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get combined settings + stats for status view."""
        settings = await NewMemberActions.get_settings(guild_id)
        stats = await NewMemberActions.get_whitelist_stats(guild_id)
        return {**settings, "whitelist_stats": stats}

    # -- Enabled toggle --------------------------------------------------

    @staticmethod
    async def get_enabled_as_list(guild_id: int) -> list:
        config = await get_config(guild_id)
        return ["true" if config.new_members.get("enabled", False) else "false"]

    @staticmethod
    async def set_enabled_from_list(guild_id: int, values: list) -> bool:
        return await NewMemberActions.set_enabled(guild_id, values[0] == "true")

    @staticmethod
    async def get_enabled(guild_id: int) -> bool:
        """Get whether New Members processing is enabled for a guild."""
        config = await get_config(guild_id)
        return config.new_members.get("enabled", False)

    @staticmethod
    async def set_enabled(guild_id: int, enabled: bool) -> bool:
        """Enable or disable New Members processing for a guild."""
        manager = await get_guild_config_manager()
        config = await manager.get_config(guild_id)
        config.new_members["enabled"] = enabled
        return await manager.save_config(config)

    @staticmethod
    async def has_channel_configured(guild_id: int) -> bool:
        """Return True if a welcome channel has been saved for this guild."""
        config = await get_config(guild_id)
        return bool(config.new_members.get("welcome_channel_id"))
