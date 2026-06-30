"""
Embed configuration loader using storage/config_manager and Color Set DB.

Provides per-guild embed settings (color sets, role-tier mappings,
description limits, feature access) via GuildConfigManager and ColorSetActions.
"""
from typing import Dict, Set, Any, Optional
from storage.logging import get_logger

logger = get_logger("EmbedConfigLoader")

# Cache settings are hardcoded globals (not per-guild)
MAX_CACHE_ENTRIES = 2000
CACHE_DURATION = 3600


class EmbedConfigLoader:
    """Load and manage embed settings from GuildConfigManager and Color Set DB."""

    # Hardcoded cache constants
    max_cache_entries = MAX_CACHE_ENTRIES
    cache_duration = CACHE_DURATION

    async def _get_gcm(self):
        """Get the global GuildConfigManager instance."""
        from storage.config_manager import get_guild_config_manager
        return await get_guild_config_manager()

    # ── Role-to-Tier Mapping ─────────────────────────────────────────
    # Stored at embed.role_tier inside GuildConfig.

    async def get_tiers_for_role(self, guild_id: int, role_id: int) -> Set[str]:
        """Get tiers for a specific role in a guild."""
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        tiers = set(mapping.get(str(role_id), []))
        logger.debug(f"Tiers for role {role_id} in guild {guild_id}: {tiers}")
        return tiers

    async def get_role_tier_mapping(self, guild_id: int) -> Dict[str, list]:
        """Get the full role-to-tier mapping for a guild."""
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        return config.embed.get("role_tier", {})

    def _resolve_user_tiers(self, role_tier_map: Dict[str, list], user_roles: Set[int]) -> Set[str]:
        """Resolve a set of role IDs to the set of tier names they grant."""
        tiers: Set[str] = set()
        for role_id in user_roles:
            tiers.update(role_tier_map.get(str(role_id), []))
        return tiers

    # ── Description Limits ───────────────────────────────────────────

    async def get_description_limit_for_user(self, guild_id: int, user_roles: Set[int]) -> int:
        """Get the effective description limit for a user based on their tier limits.

        Resolves each role to its tier(s), finds any configured tier limits, and
        returns the highest applicable limit.  Falls back to the guild default.
        """
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = config.embed.get("description_limits", {"default_limit": 500})
        default_limit = limits_data.get("default_limit", 500)
        tier_limits = limits_data.get("tier_limits", {})

        mapping = config.embed.get("role_tier", {})
        user_tiers = self._resolve_user_tiers(mapping, user_roles)

        applicable = [tier_limits[t] for t in user_tiers if t in tier_limits]
        limit = max(applicable, default=default_limit)
        logger.debug(f"Description limit for user in guild {guild_id}: tiers={user_tiers}, limit={limit}")
        return limit

    async def get_default_description_limit(self, guild_id: int) -> int:
        """Get the default description limit for a guild."""
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = config.embed.get("description_limits", {"default_limit": 500})
        return limits_data.get("default_limit", 500)

    async def get_description_limits(self, guild_id: int) -> Dict[str, Any]:
        """Get all description limits data for a guild."""
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        return config.embed.get("description_limits", {"default_limit": 500})

    # ── Colors (from Color Set DB) ────────────────────────────────────

    async def _resolve_user_color_sets(
        self, guild_id: int, user_roles: Set[int],
    ) -> list[dict]:
        """Fetch color sets accessible to a user via tier and role assignments.

        Returns the list of color set dicts (with "name", "colors", "set_id")
        that are assigned to any of the user's tiers or directly to their roles.
        """
        from commands.admin.actions.color_set_actions import ColorSetActions

        all_sets = await ColorSetActions.list_color_sets(guild_id)
        all_assignments = await ColorSetActions.list_assignments(guild_id)

        if not all_sets or not all_assignments:
            return []

        # Resolve user tiers
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        role_tier_map = config.embed.get("role_tier", {})
        user_tiers = self._resolve_user_tiers(role_tier_map, user_roles)
        user_role_strs = {str(r) for r in user_roles}

        # Find matching set IDs
        matching_set_ids: set[str] = set()
        for assignment in all_assignments:
            target_type = assignment.get("target_type", "")
            target_id = assignment.get("target_id", "")
            if target_type == "tier" and target_id in user_tiers:
                matching_set_ids.add(assignment["color_set_id"])
            elif target_type == "role" and target_id in user_role_strs:
                matching_set_ids.add(assignment["color_set_id"])

        # Filter sets
        sets_by_id = {s["set_id"]: s for s in all_sets}
        return [sets_by_id[sid] for sid in matching_set_ids if sid in sets_by_id]

    async def get_available_colors(self, guild_id: int, user_roles: Set[int]) -> Dict[str, int]:
        """Get all colors available to a user based on their tier and role assignments.

        Returns {lowercase_color_name: color_int} for validation and lookup.
        """
        user_sets = await self._resolve_user_color_sets(guild_id, user_roles)
        available: Dict[str, int] = {}
        for color_set in user_sets:
            for color in color_set.get("colors", []):
                name = color.get("name", "").lower()
                if name:
                    available[name] = color["value"]
        logger.debug(f"Available colors for user in guild {guild_id}: {len(available)} colors")
        return available

    async def get_colors_grouped_by_set(
        self, guild_id: int, user_roles: Set[int],
    ) -> Dict[str, Dict[str, int]]:
        """Get available colors grouped by color set name (for display).

        Returns {set_name: {color_name: color_int}}.
        """
        user_sets = await self._resolve_user_color_sets(guild_id, user_roles)
        grouped: Dict[str, Dict[str, int]] = {}
        for color_set in user_sets:
            set_name = color_set.get("name", "Unknown")
            colors: Dict[str, int] = {}
            for color in color_set.get("colors", []):
                name = color.get("name", "")
                if name:
                    colors[name] = color["value"]
            if colors:
                grouped[set_name] = colors
        return grouped

    async def get_default_color(self, guild_id: int) -> Optional[int]:
        """Get the server default embed color, or None if not set."""
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        return config.embed.get("default_color")

    # ── Feature Access ───────────────────────────────────────────────

    async def get_feature_access(self, guild_id: int) -> Dict[str, Set[int]]:
        """Get feature access, resolving tier names to role IDs."""
        gcm = await self._get_gcm()
        config = await gcm.get_config(guild_id)
        raw_features = config.embed.get("feature_access", {})
        role_tier_map = config.embed.get("role_tier", {})

        # Build tier -> role_ids index from the role_tier mapping
        tier_to_roles: Dict[str, Set[int]] = {}
        for role_id_str, tier_names in role_tier_map.items():
            for tier_name in tier_names:
                tier_to_roles.setdefault(tier_name, set()).add(int(role_id_str))

        # Expand each feature's tier list to role IDs
        result: Dict[str, Set[int]] = {}
        for feat, tier_names in raw_features.items():
            role_ids: Set[int] = set()
            for tier_name in tier_names:
                role_ids.update(tier_to_roles.get(tier_name, set()))
            result[feat] = role_ids
        return result

    async def get_user_features(self, guild_id: int, user_roles: Set[int]) -> Set[str]:
        """Get the set of feature names accessible to a user."""
        feature_access = await self.get_feature_access(guild_id)
        return {
            feat for feat, allowed_roles in feature_access.items()
            if not user_roles.isdisjoint(allowed_roles)
        }