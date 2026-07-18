"""
Setup Gatekeeper for TheCodex.

Fast, cached per-feature "is this configured yet?" gates used by the admin panel
so admins can't open a feature's settings before its prerequisite (WYR channel,
welcome channel, embed role-tier mapping, ...) has been set.

Uses an in-memory TimedLRUCache for fast checks.
"""

import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Optional

import discord

from storage.log import get_logger

logger = get_logger("setup_gatekeeper")


# =============================================================================
# Local TimedLRUCache (no external dependency)
# =============================================================================

class TimedLRUCache:
    """
    LRU Cache with time-based expiration.
    Items expire after a specified timeout period, in addition to LRU eviction.
    """

    def __init__(self, max_size: int = 1000, timeout: int = 300):
        """
        Initialize the timed LRU cache.

        Args:
            max_size: Maximum number of items to cache
            timeout: Expiration time in seconds (default: 300 = 5 minutes)
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self.timeout = timeout
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._timestamps: OrderedDict[str, float] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get an item from cache, checking expiration.

        Args:
            key: The cache key
            default: Default value to return if key not found or expired

        Returns:
            The cached value or default if not found/expired
        """
        if key in self._cache:
            age = time.time() - self._timestamps[key]
            if age > self.timeout:
                # Expired - remove and return default
                logger.debug(f"Cache entry expired: key={key}, age={age:.1f}s, timeout={self.timeout}s")
                self.delete(key)
                self._misses += 1
                return default

            self._hits += 1
            # Move to end (mark as recently used)
            self._cache.move_to_end(key)
            self._timestamps.move_to_end(key)
            return self._cache[key]

        self._misses += 1
        return default

    def set(self, key: str, value: Any) -> None:
        """
        Set an item in cache with current timestamp.

        Args:
            key: The cache key
            value: The value to cache
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            self._timestamps.move_to_end(key)
            self._timestamps[key] = time.time()
        elif len(self._cache) >= self.max_size:
            evicted_key = next(iter(self._cache))
            self._cache.popitem(last=False)
            self._timestamps.pop(evicted_key, None)

        self._cache[key] = value
        self._timestamps[key] = time.time()

    def delete(self, key: str) -> bool:
        """Delete an item from cache."""
        if key in self._cache:
            del self._cache[key]
            self._timestamps.pop(key, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all items from cache."""
        self._cache.clear()
        self._timestamps.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": round(hit_rate, 2)
        }


# =============================================================================
# Setup Gatekeeper
# =============================================================================

class SetupGatekeeper:
    """
    Guards per-feature admin settings behind their configuration prerequisites.

    Each feature (WYR, New Members, Embed Settings, per-tier settings) exposes a
    cached ``is_*_setup_complete`` predicate and a ``check_*_or_notify`` guard that
    sends a polite ephemeral notice when the prerequisite has not been configured.
    """

    def __init__(self):
        self._cache: TimedLRUCache = TimedLRUCache(max_size=200, timeout=120)
        self._embed_checker = None

    def set_embed_checker(self, checker) -> None:
        """
        Attach the embed setup checker callable. Must be called during startup.

        Args:
            checker: Async callable (guild_id: int) -> bool that returns True
                     if at least one role-tier mapping has been configured.
        """
        self._embed_checker = checker
        logger.info("SetupGatekeeper linked to embed checker")

    # ------------------------------------------------------------------
    # Embed Settings gate (requires role-tier mapping to be configured)
    # ------------------------------------------------------------------

    async def is_embed_setup_complete(self, guild_id: int) -> bool:
        """
        Check whether the guild has configured at least one role-tier mapping.

        Cached under the key ``embed_{guild_id}`` with the same 120 s TTL.
        Fails open (returns True) on errors so existing configurations are
        never incorrectly blocked by transient DB issues.

        Args:
            guild_id: The guild ID as an integer

        Returns:
            True if at least one tier has roles assigned
        """
        cache_key = f"embed_{guild_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            if not self._embed_checker:
                logger.warning("SetupGatekeeper has no embed_checker – failing open")
                return True

            is_complete = await self._embed_checker(guild_id)
            self._cache.set(cache_key, is_complete)
            logger.debug(
                f"Guild {guild_id} embed setup check: cached result "
                f"(complete={is_complete}, ttl=120s)"
            )
            return is_complete

        except Exception as e:
            logger.error(f"Error checking embed setup for guild {guild_id}, failing open: {e}")
            return True

    async def check_embed_or_notify(self, interaction: discord.Interaction) -> bool:
        """
        Guard for Embed Settings subcategory selections.

        If role-tier mapping hasn't been configured yet, sends an ephemeral
        embed directing the admin to configure Role Tier Mapping first and
        returns False. Otherwise returns True.

        Args:
            interaction: The Discord interaction to check

        Returns:
            True if embed setup is complete and the action may proceed
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True

        if await self.is_embed_setup_complete(guild_id):
            return True

        embed = discord.Embed(
            title="Setup Required",
            description=(
                "You need to configure **Role Tier Mapping** before accessing "
                "this section.\n\n"
                "Roles must be assigned to tiers so that description limits, "
                "color sets, and feature access have something to work with.\n\n"
                "**How to fix:**\n"
                "Select **Role Tier Mapping** and assign at least one role to a tier."
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="All other Embed Settings will unlock once a tier is configured.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.warning(f"Failed to send embed-setup-required notice: {e}")

        return False

    def invalidate_embed(self, guild_id: int) -> None:
        """Remove a guild's embed setup cache entry so the next check re-queries."""
        self._cache.delete(f"embed_{guild_id}")
        logger.debug(f"Guild {guild_id} embed setup cache invalidated")

    # ------------------------------------------------------------------
    # WYR Settings gate (requires WYR channel to be configured)
    # ------------------------------------------------------------------

    async def is_wyr_setup_complete(self, guild_id: int) -> bool:
        """Check whether the guild has a WYR channel configured.

        Cached under ``wyr_{guild_id}`` with the same 120 s TTL.
        Fails open on errors so existing configurations are never blocked
        by transient DB issues.
        """
        cache_key = f"wyr_{guild_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            from storage.config_manager import get_guild_config_manager
            gcm = await get_guild_config_manager()
            config = await gcm.get_config(guild_id)
            is_complete = bool(config.wyr.get("channel_id"))
            self._cache.set(cache_key, is_complete)
            logger.debug(
                f"Guild {guild_id} WYR setup check: cached result "
                f"(complete={is_complete}, ttl=120s)"
            )
            return is_complete

        except Exception as e:
            logger.error(f"Error checking WYR setup for guild {guild_id}, failing open: {e}")
            return True

    async def check_wyr_or_notify(self, interaction: discord.Interaction) -> bool:
        """Guard for WYR settings other than the channel selector.

        If the WYR channel has not been configured yet, sends an ephemeral
        embed directing the admin to set the channel first and returns False.
        Otherwise returns True.
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True

        if await self.is_wyr_setup_complete(guild_id):
            return True

        embed = discord.Embed(
            title="WYR Channel Required",
            description=(
                "A **WYR Channel** must be configured before these settings "
                "can be changed.\n\n"
                "**How to fix:**\n"
                "Select **WYR Channel** and choose the channel where questions "
                "will be posted. All other WYR settings will unlock immediately."
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Once a channel is set, all WYR settings will become available.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.warning(f"Failed to send WYR-setup-required notice: {e}")

        return False

    def invalidate_wyr(self, guild_id: int) -> None:
        """Remove a guild's WYR setup cache entry so the next check re-queries."""
        self._cache.delete(f"wyr_{guild_id}")
        logger.debug(f"Guild {guild_id} WYR setup cache invalidated")

    # ------------------------------------------------------------------
    # New Members Settings gate (requires welcome_channel_id to be configured)
    # ------------------------------------------------------------------

    async def is_new_members_setup_complete(self, guild_id: int) -> bool:
        """Check whether the guild has a welcome channel configured for New Members.

        Cached under ``new_members_{guild_id}`` with the same 120 s TTL.
        Fails open on errors so existing configurations are never blocked
        by transient DB issues.
        """
        cache_key = f"new_members_{guild_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            from storage.config_manager import get_guild_config_manager
            gcm = await get_guild_config_manager()
            config = await gcm.get_config(guild_id)
            is_complete = bool(config.new_members.get("welcome_channel_id"))
            self._cache.set(cache_key, is_complete)
            logger.debug(
                f"Guild {guild_id} New Members setup check: cached result "
                f"(complete={is_complete}, ttl=120s)"
            )
            return is_complete

        except Exception as e:
            logger.error(f"Error checking New Members setup for guild {guild_id}, failing open: {e}")
            return True

    async def check_new_members_or_notify(self, interaction: discord.Interaction) -> bool:
        """Guard for New Members settings that require welcome_channel_id.

        If the welcome channel has not been configured yet, sends an ephemeral
        embed directing the admin to set the channel first and returns False.
        Otherwise returns True.
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True

        if await self.is_new_members_setup_complete(guild_id):
            return True

        embed = discord.Embed(
            title="Welcome Channel Required",
            description=(
                "A **Welcome Channel** must be configured before these settings "
                "can be changed.\n\n"
                "**How to fix:**\n"
                "Select **Welcome Channel** and choose the channel where welcome "
                "messages will be sent. All other New Member settings will unlock immediately."
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Once a channel is set, all New Member settings will become available.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.warning(f"Failed to send New Members setup-required notice: {e}")

        return False

    def invalidate_new_members(self, guild_id: int) -> None:
        """Remove a guild's New Members setup cache entry so the next check re-queries."""
        self._cache.delete(f"new_members_{guild_id}")
        logger.debug(f"Guild {guild_id} New Members setup cache invalidated")

    # ------------------------------------------------------------------
    # Per-tier gate (requires specific tier to have roles assigned)
    # ------------------------------------------------------------------

    async def is_tier_ready(self, guild_id: int, tier_name: str) -> bool:
        """Check whether a specific tier has at least one role assigned.

        Cached under ``tier_{guild_id}_{tier_name}`` with the same 120 s TTL.
        Fails open on errors so existing configurations are never blocked
        by transient DB issues.

        Args:
            guild_id:  The guild ID as an integer
            tier_name: Tier key — one of "tier_1" … "tier_5"

        Returns:
            True if at least one role is mapped to this tier
        """
        cache_key = f"tier_{guild_id}_{tier_name}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            from storage.config_manager import get_guild_config_manager
            gcm = await get_guild_config_manager()
            config = await gcm.get_config(guild_id)
            role_tier_map = config.embed.get("role_tier", {})
            is_ready = any(tier_name in tiers for tiers in role_tier_map.values())
            self._cache.set(cache_key, is_ready)
            logger.debug(
                f"Guild {guild_id} tier '{tier_name}' ready check: "
                f"cached result (ready={is_ready}, ttl=120s)"
            )
            return is_ready

        except Exception as e:
            logger.error(
                f"Error checking tier '{tier_name}' for guild {guild_id}, failing open: {e}"
            )
            return True  # Fail open

    def build_tier_not_configured_layout(self, tier_name: str) -> discord.ui.LayoutView:
        """Build the 'tier not configured' Components v2 notice LayoutView.

        Returns a Message-3 style notice (orange container) per
        ADMIN_PANEL_STANDARD.md §0.1 — no embeds on admin panels.
        """
        from commands.admin.views.base import build_notice_layout

        tier_label = tier_name.replace("_", " ").title()  # "tier_3" → "Tier 3"
        body = (
            f"**{tier_label}** has no roles assigned yet.\n\n"
            "Settings for this tier have no effect until at least one role is "
            "mapped to it — so saving here would create dead configuration.\n\n"
            "**How to fix:**\n"
            "Go back and select **Role Tier Mapping**, then assign at least one "
            f"role to {tier_label}.\n\n"
            f"_Once {tier_label} has roles assigned, this setting will unlock._"
        )
        return build_notice_layout("Tier Not Configured", body)

    async def get_tier_gate_layout(
        self, guild_id: int, tier_name: str
    ) -> "discord.ui.LayoutView | None":
        """Return a notice LayoutView if the tier has no roles, or None if allowed.

        Designed for panel contexts where the caller must control the response
        sequence: edit_message (to reset the dropdown) before followup (notification).
        """
        if await self.is_tier_ready(guild_id, tier_name):
            return None
        return self.build_tier_not_configured_layout(tier_name)

    async def check_tier_or_notify(
        self, interaction: discord.Interaction, tier_name: str
    ) -> bool:
        """Guard for tier-specific settings.

        Sends an ephemeral notification and returns False if the tier has no roles.
        Returns True if the tier is ready. Use get_tier_gate_layout instead when
        you need to reset a dropdown before sending the notification.
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True

        layout = await self.get_tier_gate_layout(guild_id, tier_name)
        if layout is None:
            return True

        try:
            if interaction.response.is_done():
                await interaction.followup.send(view=layout, ephemeral=True)
            else:
                await interaction.response.send_message(view=layout, ephemeral=True)
        except Exception as e:
            logger.warning(f"Failed to send tier-not-configured notice: {e}")

        return False

    def invalidate_tier(self, guild_id: int, tier_name: str) -> None:
        """Remove a tier-ready cache entry so the next check re-queries."""
        self._cache.delete(f"tier_{guild_id}_{tier_name}")
        logger.debug(f"Guild {guild_id} tier '{tier_name}' cache invalidated")

    def invalidate_all_tiers(self, guild_id: int) -> None:
        """Invalidate all five tier-ready cache entries for a guild."""
        for tier in ("tier_1", "tier_2", "tier_3", "tier_4", "tier_5"):
            self.invalidate_tier(guild_id, tier)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate(self, guild_id: int):
        """Remove a single guild from the cache."""
        self._cache.delete(str(guild_id))
        logger.debug(f"Guild {guild_id} cache invalidated")

    def invalidate_all(self):
        """Clear the entire cache."""
        self._cache.clear()

    def get_stats(self) -> dict:
        """Return cache statistics for diagnostics."""
        return self._cache.get_stats()


# Global singleton
setup_gatekeeper = SetupGatekeeper()
