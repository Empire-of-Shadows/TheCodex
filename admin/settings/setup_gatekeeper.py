"""
Setup Gatekeeper for TheCodex.

Fast, cached per-feature "is this configured yet?" gates used by the admin panel
so admins can't open a feature's settings before its prerequisite (WYR channel,
greeting channel, embed role-tier mapping, ...) has been set.

Each feature predicate delegates to an engine ``SetupGate`` (cached, fail-open); this
class keeps only the codex-specific requirement definitions and the discord-facing
``check_*_or_notify`` guards / tier-gate layouts.
"""

import discord

from storage.log import get_logger
# Each feature predicate delegates to the engine SetupGate (cached + fail-open); the bot
# no longer hand-rolls the caching/predicate machinery.
from storage.services import SetupGate

logger = get_logger("setup_gatekeeper")

_TIERS = ("tier_1", "tier_2", "tier_3", "tier_4", "tier_5")


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
        self._embed_checker = None
        # One engine SetupGate per feature predicate (each keeps its own bounded,
        # time-expiring cache and fails open on loader errors). The discord-facing
        # check_*_or_notify guards below stay in the bot.
        self._embed_gate = SetupGate(self._load_embed_state, self._embed_requirement)
        self._wyr_gate = SetupGate(self._load_config, self._wyr_requirement)
        self._new_members_gate = SetupGate(self._load_config, self._new_members_requirement)
        self._tier_gates = {
            tier: SetupGate(self._load_config, self._tier_requirement(tier))
            for tier in _TIERS
        }

    # ------------------------------------------------------------------
    # Loaders + requirement predicates (feed the SetupGate instances)
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_config(guild_id: int):
        """Async config loader shared by the wyr / new_members / tier gates."""
        from storage.settings.config_manager import get_guild_config_manager
        gcm = await get_guild_config_manager()
        return await gcm.get_config(guild_id)

    async def _load_embed_state(self, guild_id: int) -> dict:
        """Embed gate loader: wraps the injected embed checker. Fails open (complete)
        when no checker has been linked yet."""
        if self._embed_checker is None:
            logger.warning("SetupGatekeeper has no embed_checker - failing open")
            return {"complete": True}
        return {"complete": await self._embed_checker(guild_id)}

    @staticmethod
    def _embed_requirement(state) -> bool:
        return bool(state.get("complete"))

    @staticmethod
    def _wyr_requirement(config) -> bool:
        return bool(config.wyr.get("channel_id"))

    @staticmethod
    def _new_members_requirement(config) -> bool:
        return bool(config.new_members.get("greeting_channel_id"))

    @staticmethod
    def _tier_requirement(tier_name: str):
        def requirement(config) -> bool:
            role_tier_map = config.embed.get("role_tier", {})
            return any(tier_name in tiers for tiers in role_tier_map.values())
        return requirement

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
        return await self._embed_gate.is_complete(guild_id)

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
        self._embed_gate.invalidate(guild_id)
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
        return await self._wyr_gate.is_complete(guild_id)

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
        self._wyr_gate.invalidate(guild_id)
        logger.debug(f"Guild {guild_id} WYR setup cache invalidated")

    # ------------------------------------------------------------------
    # New Members Settings gate (requires greeting_channel_id to be configured)
    # ------------------------------------------------------------------

    async def is_new_members_setup_complete(self, guild_id: int) -> bool:
        """Check whether the guild has a greeting channel configured for New Members.

        Cached under ``new_members_{guild_id}`` with the same 120 s TTL.
        Fails open on errors so existing configurations are never blocked
        by transient DB issues.
        """
        return await self._new_members_gate.is_complete(guild_id)

    async def check_new_members_or_notify(self, interaction: discord.Interaction) -> bool:
        """Guard for New Members settings that require greeting_channel_id.

        If the greeting channel has not been configured yet, sends an ephemeral
        embed directing the admin to set the channel first and returns False.
        Otherwise returns True.
        """
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return True

        if await self.is_new_members_setup_complete(guild_id):
            return True

        embed = discord.Embed(
            title="Greeting Channel Required",
            description=(
                "A **Greeting Channel** must be configured before these settings "
                "can be changed.\n\n"
                "**How to fix:**\n"
                "Select **Greeting Channel** and choose the channel where greeting "
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
        self._new_members_gate.invalidate(guild_id)
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
            tier_name: Tier key - one of "tier_1" … "tier_5"

        Returns:
            True if at least one role is mapped to this tier
        """
        gate = self._tier_gates.get(tier_name)
        if gate is None:
            return True  # Unknown tier -> fail open
        return await gate.is_complete(guild_id)

    def build_tier_not_configured_layout(self, tier_name: str) -> discord.ui.LayoutView:
        """Build the 'tier not configured' Components v2 notice LayoutView.

        Returns a Message-3 style notice (orange container) per
        ADMIN_PANEL_STANDARD.md §0.1 - no embeds on admin panels.
        """
        from ..views.base import build_notice_layout

        tier_label = tier_name.replace("_", " ").title()  # "tier_3" → "Tier 3"
        body = (
            f"**{tier_label}** has no roles assigned yet.\n\n"
            "Settings for this tier have no effect until at least one role is "
            "mapped to it - so saving here would create dead configuration.\n\n"
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
        gate = self._tier_gates.get(tier_name)
        if gate is not None:
            gate.invalidate(guild_id)
        logger.debug(f"Guild {guild_id} tier '{tier_name}' cache invalidated")

    def invalidate_all_tiers(self, guild_id: int) -> None:
        """Invalidate all five tier-ready cache entries for a guild."""
        for tier in ("tier_1", "tier_2", "tier_3", "tier_4", "tier_5"):
            self.invalidate_tier(guild_id, tier)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate(self, guild_id: int):
        """Remove a guild from EVERY feature gate's cache. (Previously this deleted a
        bare ``str(guild_id)`` key that no gate ever wrote, so it invalidated nothing.)"""
        self._embed_gate.invalidate(guild_id)
        self._wyr_gate.invalidate(guild_id)
        self._new_members_gate.invalidate(guild_id)
        self.invalidate_all_tiers(guild_id)
        logger.debug(f"Guild {guild_id} cache invalidated")

    def invalidate_all(self):
        """Clear every feature gate's cache."""
        self._embed_gate.invalidate_all()
        self._wyr_gate.invalidate_all()
        self._new_members_gate.invalidate_all()
        for gate in self._tier_gates.values():
            gate.invalidate_all()

    def get_stats(self) -> dict:
        """Return per-gate cache statistics for diagnostics."""
        stats = {
            "embed": self._embed_gate.get_stats(),
            "wyr": self._wyr_gate.get_stats(),
            "new_members": self._new_members_gate.get_stats(),
        }
        for tier, gate in self._tier_gates.items():
            stats[tier] = gate.get_stats()
        return stats


# Global singleton
setup_gatekeeper = SetupGatekeeper()
