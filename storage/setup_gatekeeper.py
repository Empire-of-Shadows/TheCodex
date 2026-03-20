"""
Setup Gatekeeper for ImperialHost

Blocks all bot processing (game commands) for guilds that haven't completed
minimum setup. The only hard requirement is that game_category_id must be configured.

Uses an in-memory TimedLRUCache for fast event listener checks.
"""

import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Optional

import discord

from utils.logger import get_logger

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
    Guards bot functionality behind a minimum setup requirement.

    Guilds must have at least `game_category_id` configured before any game
    commands will function. The `/admin panel` command is always allowed so
    admins can complete setup.
    """

    def __init__(self):
        self._cache: TimedLRUCache = TimedLRUCache(max_size=200, timeout=120)
        self._config_manager = None
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

    def set_config_manager(self, config_manager):
        """
        Attach the config manager instance. Must be called during startup.

        Args:
            config_manager: Initialized ConfigManager instance
        """
        self._config_manager = config_manager
        logger.info("SetupGatekeeper linked to ConfigManager")

    # ------------------------------------------------------------------
    # Fast cached check (for event listeners)
    # ------------------------------------------------------------------

    async def is_setup_complete(self, guild_id: int) -> bool:
        """
        Check whether a guild has completed minimum setup.

        Returns a cached result when available (120s TTL).
        On cache miss, queries ConfigManager.
        Fails open on DB errors so configured guilds aren't blocked
        by transient database issues.

        Args:
            guild_id: The guild ID as an integer

        Returns:
            True if setup is complete, False otherwise
        """
        cache_key = str(guild_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Guild {guild_id} setup check: cache hit (complete={cached})")
            return cached

        # Cache miss – query config manager
        logger.debug(f"Guild {guild_id} setup check: cache miss, querying config")
        try:
            if not self._config_manager:
                logger.warning("SetupGatekeeper has no config_manager – failing open")
                return True

            is_complete = await self._evaluate_requirements(guild_id)
            self._cache.set(cache_key, is_complete)
            logger.debug(f"Guild {guild_id} setup check: cached result (complete={is_complete}, ttl=120s)")
            return is_complete

        except Exception as e:
            logger.error(f"Error checking setup for guild {guild_id}, failing open: {e}")
            return True  # Fail open

    # ------------------------------------------------------------------
    # Slash-command guard (polite ephemeral embed)
    # ------------------------------------------------------------------

    async def check_or_notify(self, interaction: discord.Interaction) -> bool:
        """
        Guard for slash commands. If setup is incomplete, sends an
        ephemeral embed directing the admin to `/admin panel` and
        returns False. Otherwise returns True.

        Args:
            interaction: The Discord interaction to check

        Returns:
            True if the guild is set up and the command may proceed
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True  # DMs – let it through

        if await self.is_setup_complete(guild_id):
            return True

        # Build a polite notification embed
        embed = discord.Embed(
            title="Bot Setup Required",
            description=(
                "This server hasn't finished setting up the bot yet.\n\n"
                "An administrator needs to configure the **Game Category** "
                "before game features become available.\n\n"
                "**How to fix:**\n"
                "`/admin panel` → **Configure Channels**"
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Once setup is complete, all game commands will unlock automatically.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.warning(f"Failed to send setup-required embed: {e}")

        return False

    # ------------------------------------------------------------------
    # Re-evaluate and persist (called after admin saves channel config)
    # ------------------------------------------------------------------

    async def evaluate_and_update(self, guild_id: int) -> bool:
        """
        Re-evaluate setup requirements and invalidate the cache entry.

        Args:
            guild_id: The guild ID as an integer

        Returns:
            True if the guild now meets all requirements
        """
        try:
            if not self._config_manager:
                logger.warning("SetupGatekeeper has no config_manager")
                return False

            is_complete = await self._evaluate_requirements(guild_id)

            # Persist setup_complete status
            await self._config_manager.set("setup_complete", is_complete, guild_id)

            self.invalidate(guild_id)
            logger.info(f"Guild {guild_id} setup_complete evaluated to {is_complete}")
            return is_complete

        except Exception as e:
            logger.error(f"Error in evaluate_and_update for guild {guild_id}: {e}", exc_info=True)
            self.invalidate(guild_id)
            return False

    # ------------------------------------------------------------------
    # Channel deletion handler
    # ------------------------------------------------------------------

    async def on_channel_deleted(self, guild_id: int, channel_id: int):
        """
        If the deleted channel was the game_category_id, clear it
        from settings and revert setup_complete to False.

        Args:
            guild_id: The guild ID as an integer
            channel_id: The deleted channel ID as an integer
        """
        try:
            if not self._config_manager:
                return

            game_category_id = await self._config_manager.game_category_id(guild_id)
            if game_category_id != channel_id:
                return  # Not the game category – nothing to do

            logger.warning(
                f"Game category {channel_id} deleted in guild {guild_id}, "
                "reverting setup_complete to False"
            )

            await self._config_manager.set("game_category_id", None, guild_id)
            await self._config_manager.set("setup_complete", False, guild_id)

            self.invalidate(guild_id)

        except Exception as e:
            logger.error(
                f"Error handling channel deletion for guild {guild_id}: {e}",
                exc_info=True,
            )
            self.invalidate(guild_id)

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

    def build_tier_not_configured_embed(self, tier_name: str) -> discord.Embed:
        """Build the 'tier not configured' notification embed without sending it.

        Separated from the send logic so callers can control the response
        sequence (e.g. edit_message first to reset a dropdown, then followup).

        Args:
            tier_name: Tier key — one of "tier_1" … "tier_5"

        Returns:
            A discord.Embed ready to send
        """
        tier_label = tier_name.replace("_", " ").title()  # "tier_3" → "Tier 3"
        embed = discord.Embed(
            title="Tier Not Configured",
            description=(
                f"**{tier_label}** has no roles assigned yet.\n\n"
                "Settings for this tier have no effect until at least one role is "
                "mapped to it — so saving here would create dead configuration.\n\n"
                "**How to fix:**\n"
                "Go back and select **Role Tier Mapping**, then assign at least one "
                f"role to {tier_label}."
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"Once {tier_label} has roles assigned, this setting will unlock.")
        return embed

    async def get_tier_gate_embed(
        self, guild_id: int, tier_name: str
    ) -> "discord.Embed | None":
        """Return the notification embed if a tier has no roles, or None if allowed.

        Designed for panel contexts where the caller must control the response
        sequence: edit_message (to reset the dropdown) before followup (notification).

        Args:
            guild_id:  The guild ID as an integer
            tier_name: Tier key — one of "tier_1" … "tier_5"

        Returns:
            None if the tier is configured and the action may proceed,
            or a discord.Embed to display if the tier has no roles yet
        """
        if await self.is_tier_ready(guild_id, tier_name):
            return None
        return self.build_tier_not_configured_embed(tier_name)

    async def check_tier_or_notify(
        self, interaction: discord.Interaction, tier_name: str
    ) -> bool:
        """Guard for tier-specific settings.

        Sends an ephemeral notification and returns False if the tier has no roles.
        Returns True if the tier is ready. Use get_tier_gate_embed instead when
        you need to reset a dropdown before sending the notification.

        Args:
            interaction: The Discord interaction to check
            tier_name:   Tier key — one of "tier_1" … "tier_5"

        Returns:
            True if the tier has roles and the action may proceed
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True

        embed = await self.get_tier_gate_embed(guild_id, tier_name)
        if embed is None:
            return True

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
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

    # ------------------------------------------------------------------
    # Bot Permission Checker
    # ------------------------------------------------------------------

    async def check_bot_permissions(
        self,
        guild: discord.Guild,
        channel: discord.abc.GuildChannel | None = None
    ) -> tuple[bool, list[str]]:
        """
        Validate that the bot has required permissions in the guild/channel.

        Required permissions for full functionality:
        - send_messages: Send messages in channels
        - embed_links: Send embeds for game UI
        - manage_channels: Create/delete game channels
        - add_reactions: Add reactions for game feedback

        Optional but recommended:
        - manage_messages: Delete invalid messages in counting
        - read_message_history: Required for some game features
        - manage_threads: Create discussion threads for games

        Args:
            guild: The Discord guild to check
            channel: Optional specific channel to check (uses guild-wide if None)

        Returns:
            Tuple of (all_required_present, list_of_missing_permissions)
        """
        # Define required permissions
        required_permissions = [
            ("send_messages", "Send Messages"),
            ("embed_links", "Embed Links"),
            ("manage_channels", "Manage Channels"),
            ("add_reactions", "Add Reactions"),
        ]

        # Define recommended permissions (logged as warnings if missing)
        recommended_permissions = [
            ("manage_messages", "Manage Messages"),
            ("read_message_history", "Read Message History"),
        ]

        missing_required = []
        missing_recommended = []

        # Get bot's permissions
        if channel:
            # Check channel-specific permissions
            perms = channel.permissions_for(guild.me)
        else:
            # Check guild-wide permissions
            perms = guild.me.guild_permissions

        # Check required permissions
        for perm_attr, perm_name in required_permissions:
            if not getattr(perms, perm_attr, False):
                missing_required.append(perm_name)

        # Check recommended permissions (just for logging)
        for perm_attr, perm_name in recommended_permissions:
            if not getattr(perms, perm_attr, False):
                missing_recommended.append(perm_name)

        # Log warnings for missing recommended permissions
        if missing_recommended:
            logger.warning(
                f"Guild {guild.id} is missing recommended permissions: "
                f"{', '.join(missing_recommended)}"
            )

        all_present = len(missing_required) == 0

        if not all_present:
            logger.warning(
                f"Guild {guild.id} is missing required permissions: "
                f"{', '.join(missing_required)}"
            )

        return all_present, missing_required

    async def check_category_permissions(
        self,
        guild: discord.Guild,
        category_id: int | None
    ) -> tuple[bool, list[str]]:
        """
        Check if the bot has required permissions in the game category.

        Args:
            guild: The Discord guild
            category_id: The category ID to check

        Returns:
            Tuple of (all_required_present, list_of_missing_permissions)
        """
        if not category_id:
            return False, ["No game category configured"]

        category = guild.get_channel(category_id)
        if not category:
            return False, ["Game category not found"]

        if not isinstance(category, discord.CategoryChannel):
            return False, ["Configured channel is not a category"]

        return await self.check_bot_permissions(guild, category)

    def build_permission_warning_embed(
        self,
        missing_permissions: list[str],
        category_name: str | None = None
    ) -> discord.Embed:
        """
        Build an embed warning about missing permissions.

        Args:
            missing_permissions: List of missing permission names
            category_name: Optional category name for context

        Returns:
            Discord embed with permission warning
        """
        location = f"the **{category_name}** category" if category_name else "this server"

        embed = discord.Embed(
            title="Missing Bot Permissions",
            description=(
                f"I'm missing some permissions required to run games in {location}.\n\n"
                "Please ask a server administrator to grant these permissions:"
            ),
            color=discord.Color.orange(),
        )

        permission_list = "\n".join(f"- {perm}" for perm in missing_permissions)
        embed.add_field(
            name="Missing Permissions",
            value=permission_list,
            inline=False,
        )

        embed.add_field(
            name="How to Fix",
            value=(
                "1. Go to **Server Settings** > **Roles**\n"
                "2. Find the ImperialHost role\n"
                "3. Enable the missing permissions\n"
                "4. Or check the category's permission overwrites"
            ),
            inline=False,
        )

        embed.set_footer(text="Games will work once permissions are granted.")

        return embed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _evaluate_requirements(self, guild_id: int) -> bool:
        """
        Check whether the guild settings meet the minimum requirements.

        Currently the only hard requirement is that game_category_id
        is set to a non-None value.

        Args:
            guild_id: The guild ID

        Returns:
            True if all requirements are met
        """
        if not self._config_manager:
            return False

        game_category_id = await self._config_manager.game_category_id(guild_id)
        if not game_category_id:
            return False

        return True


# Global singleton
setup_gatekeeper = SetupGatekeeper()
