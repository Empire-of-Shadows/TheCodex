"""
Embed Config Actions - Business logic for embed configuration via admin panel.

All read/write goes through storage.config_manager (GuildConfigManager).
All embed settings live inside config.embed on the GuildConfig dataclass:
  embed.role_tier          - role-to-tier mapping
  embed.description_limits - default_limit, limits, tier_limits
  embed.feature_access     - feature -> [tier_names]
  embed.free_color_access  - bool, guild-wide opt-out from color restrictions

``feature_access`` values are TIER NAMES, never role IDs. The old
``set_feature_roles`` writer stored role-id strings into the same slot, which no
reader ever understood; it had no callers and was removed 2026-08-12.

Member-selectable colors are NOT here: they live in the Color Set collections
(``admin/actions/color_set_actions.py``). The old ``embed.color_tiers`` dict this module
used to manage was superseded by that system and is removed by migration m12.
"""

from typing import Any, Dict, List, Optional

import discord

from storage.log import get_logger
from ..views.base import AdminLayoutBuilder, cid, readonly_container
from ..views.panel_engine import ActionContext, PanelNode, build_confirm_view
from .panel_flow import PanelFlow

logger = get_logger("EmbedConfigActions")


async def _get_gcm():
    """Get the global GuildConfigManager instance."""
    from storage.settings.config_manager import get_guild_config_manager
    return await get_guild_config_manager()


class EmbedConfigActions:
    """Static async methods for managing embed configuration."""

    # ── Role Tier Mapping ────────────────────────────────────────────
    # Stored at embed.role_tier inside GuildConfig.

    # Predefined tier names (up to 5)
    TIER_NAMES = ["tier_1", "tier_2", "tier_3", "tier_4", "tier_5"]

    @staticmethod
    async def get_role_tier_mapping(guild_id: int) -> Dict[str, list]:
        """Get the full role-to-tier mapping for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.embed.get("role_tier", {})

    @staticmethod
    async def has_any_tier_configured(guild_id: int) -> bool:
        """Return True if at least one role has been assigned to any tier."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return bool(config.embed.get("role_tier", {}))

    @staticmethod
    async def get_tier_to_role_mapping(guild_id: int) -> Dict[str, Optional[int]]:
        """Get an inverted mapping of tier_name -> role_id (or None if unassigned)."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        tier_to_role: Dict[str, Optional[int]] = {t: None for t in EmbedConfigActions.TIER_NAMES}
        for role_id_str, tiers in mapping.items():
            for tier in tiers:
                if tier in tier_to_role:
                    tier_to_role[tier] = int(role_id_str)
        return tier_to_role

    @staticmethod
    async def assign_tier_to_role(guild_id: int, tier_name: str, role_id: int) -> bool:
        """Assign a tier to a role, ensuring 1:1 mapping (removes tier from any other role first)."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        # Remove this tier from any existing role
        for rid_str in list(mapping.keys()):
            if tier_name in mapping[rid_str]:
                mapping[rid_str].remove(tier_name)
                if not mapping[rid_str]:
                    del mapping[rid_str]
        # Assign the tier to the new role
        role_id_str = str(role_id)
        mapping.setdefault(role_id_str, [])
        if tier_name not in mapping[role_id_str]:
            mapping[role_id_str].append(tier_name)
        config.embed["role_tier"] = mapping
        return await gcm.save_config(config)

    @staticmethod
    async def clear_tier(guild_id: int, tier_name: str) -> bool:
        """Remove a tier assignment (unassign from whatever role it's on)."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        for rid_str in list(mapping.keys()):
            if tier_name in mapping[rid_str]:
                mapping[rid_str].remove(tier_name)
                if not mapping[rid_str]:
                    del mapping[rid_str]
        config.embed["role_tier"] = mapping
        return await gcm.save_config(config)

    @staticmethod
    async def set_role_tiers(guild_id: int, role_id: int, tiers: List[str]) -> bool:
        """Set tiers for a specific role."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        mapping[str(role_id)] = tiers
        config.embed["role_tier"] = mapping
        return await gcm.save_config(config)

    @staticmethod
    async def set_roles_for_tier(guild_id: int, tier_name: str, role_ids: List[int]) -> bool:
        """Replace all role assignments for a specific tier (many-to-many).

        Removes tier_name from every role that currently has it, then adds it
        to each role in role_ids.  Other tiers on those roles are untouched.
        """
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        # Strip tier from all current holders
        for rid_str in list(mapping.keys()):
            if tier_name in mapping[rid_str]:
                mapping[rid_str].remove(tier_name)
                if not mapping[rid_str]:
                    del mapping[rid_str]
        # Assign tier to each selected role
        for role_id in role_ids:
            role_id_str = str(role_id)
            mapping.setdefault(role_id_str, [])
            if tier_name not in mapping[role_id_str]:
                mapping[role_id_str].append(tier_name)
        config.embed["role_tier"] = mapping
        return await gcm.save_config(config)

    @staticmethod
    async def remove_role_tier(guild_id: int, role_id: int) -> bool:
        """Remove a role from the tier mapping."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        mapping = config.embed.get("role_tier", {})
        mapping.pop(str(role_id), None)
        config.embed["role_tier"] = mapping
        return await gcm.save_config(config)

    # ── Description Limits ───────────────────────────────────────────

    _DL_DEFAULT = {"default_limit": 500, "limits": {}}

    @staticmethod
    async def get_description_limits(guild_id: int) -> Dict[str, Any]:
        """Get all description limits for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        data = dict(config.embed.get("description_limits", EmbedConfigActions._DL_DEFAULT))
        data.setdefault("tier_limits", {})
        return data

    @staticmethod
    async def set_description_limit(guild_id: int, role_id: int, limit: int) -> bool:
        """Set a description limit for a specific role."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = dict(config.embed.get("description_limits", EmbedConfigActions._DL_DEFAULT))
        limits_data.setdefault("limits", {})[str(role_id)] = limit
        config.embed["description_limits"] = limits_data
        return await gcm.save_config(config)

    @staticmethod
    async def set_default_limit(guild_id: int, limit: int) -> bool:
        """Set the default description limit."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = dict(config.embed.get("description_limits", EmbedConfigActions._DL_DEFAULT))
        limits_data["default_limit"] = limit
        config.embed["description_limits"] = limits_data
        return await gcm.save_config(config)

    @staticmethod
    async def remove_limit(guild_id: int, role_id: int) -> bool:
        """Remove a role-specific description limit."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = dict(config.embed.get("description_limits", EmbedConfigActions._DL_DEFAULT))
        limits_data.get("limits", {}).pop(str(role_id), None)
        config.embed["description_limits"] = limits_data
        return await gcm.save_config(config)

    @staticmethod
    async def set_tier_description_limit(guild_id: int, tier_name: str, limit: int) -> bool:
        """Set a description limit for a specific tier."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = dict(config.embed.get("description_limits", EmbedConfigActions._DL_DEFAULT))
        limits_data.setdefault("tier_limits", {})[tier_name] = limit
        config.embed["description_limits"] = limits_data
        return await gcm.save_config(config)

    @staticmethod
    async def remove_tier_description_limit(guild_id: int, tier_name: str) -> bool:
        """Remove a tier-specific description limit."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        limits_data = dict(config.embed.get("description_limits", EmbedConfigActions._DL_DEFAULT))
        limits_data.get("tier_limits", {}).pop(tier_name, None)
        config.embed["description_limits"] = limits_data
        return await gcm.save_config(config)

    # ── Feature Access ───────────────────────────────────────────────

    @staticmethod
    async def get_feature_access(guild_id: int) -> Dict[str, list]:
        """Get feature access config for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.embed.get("feature_access", {})

    @staticmethod
    async def set_feature_tiers(guild_id: int, feature: str, tier_names: List[str]) -> bool:
        """Set which tiers can access a feature (stores tier name strings)."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        features = dict(config.embed.get("feature_access", {}))
        features[feature] = list(tier_names)
        config.embed["feature_access"] = features
        return await gcm.save_config(config)

    @staticmethod
    async def get_roles_for_tier(guild_id: int, tier_name: str) -> list:
        """Get role IDs currently assigned to a specific tier."""
        mapping = await EmbedConfigActions.get_role_tier_mapping(guild_id)
        return [int(rid_str) for rid_str, tiers in mapping.items() if tier_name in tiers]

    @staticmethod
    async def get_tiers_for_feature(guild_id: int, feature: str) -> list:
        """Get tier names currently granted access to a specific feature."""
        features = await EmbedConfigActions.get_feature_access(guild_id)
        return list(features.get(feature, []))

    @staticmethod
    async def remove_feature(guild_id: int, feature: str) -> bool:
        """Remove a feature from the access list."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        features = dict(config.embed.get("feature_access", {}))
        features.pop(feature, None)
        config.embed["feature_access"] = features
        return await gcm.save_config(config)

    # ── Free Color Access ────────────────────────────────────────────
    # Stored at embed.free_color_access. Missing reads as False, so no migration
    # is needed to introduce it: colors follow the color-set assignments unless
    # an admin deliberately opens them up to everyone.

    @staticmethod
    async def get_free_color_access(guild_id: int) -> bool:
        """Whether every member may use any hex color in this guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return bool(config.embed.get("free_color_access", False))

    @staticmethod
    async def set_free_color_access(guild_id: int, enabled: bool) -> bool:
        """Open embed colors up to everyone, or put them back behind the palettes."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.embed["free_color_access"] = bool(enabled)
        return await gcm.save_config(config)

    # ── Status / Overview ────────────────────────────────────────────

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Get a detailed summary of all embed config for a guild."""
        from .color_set_actions import ColorSetActions
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)

        # Role tier mapping - invert to {tier_name: [role_id, ...]}
        raw_mapping = config.embed.get("role_tier", {})
        tier_roles: Dict[str, List[int]] = {t: [] for t in EmbedConfigActions.TIER_NAMES}
        for role_id_str, tiers in raw_mapping.items():
            for t in tiers:
                if t in tier_roles:
                    tier_roles[t].append(int(role_id_str))

        # Description limits
        limits = config.embed.get("description_limits", {"default_limit": 500, "limits": {}})

        # Feature access
        features: Dict[str, list] = config.embed.get("feature_access", {})

        # Color sets with per-set assignment details
        color_sets = await ColorSetActions.list_color_sets(guild_id)
        all_assignments = await ColorSetActions.list_assignments(guild_id)
        assignments_by_set: Dict[str, list] = {}
        for a in all_assignments:
            assignments_by_set.setdefault(a["color_set_id"], []).append(a)

        color_set_summaries = [
            {
                "name": cs["name"],
                "color_count": len(cs.get("colors", [])),
                "assignments": assignments_by_set.get(cs["set_id"], []),
            }
            for cs in color_sets
        ]

        return {
            "setup_complete": config.setup_complete,
            "tier_roles": tier_roles,
            "default_limit": limits.get("default_limit", 500),
            "tier_limits": limits.get("tier_limits", {}),
            "color_sets": color_set_summaries,
            "feature_access": features,
            "free_color_access": bool(config.embed.get("free_color_access", False)),
        }

    # -- Enabled toggle --------------------------------------------------

    @staticmethod
    async def get_enabled(guild_id: int) -> bool:
        """Get whether Embed creation is enabled for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        return config.embed.get("enabled", False)

    @staticmethod
    async def set_enabled(guild_id: int, enabled: bool) -> bool:
        """Enable or disable Embed creation for a guild."""
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        config.embed["enabled"] = enabled
        return await gcm.save_config(config)


# ── Free Color Access panel node ─────────────────────────────────────────────
# A bespoke ``action`` node rather than an option_select toggle, because turning
# it ON hands every member in the server free rein over embed colors and the
# owner wants that confirmed deliberately. Turning it back OFF is immediate -
# tightening a permission never needs a confirmation step.
#
# Node contract (see TheCodex CLAUDE.md, "Admin panel / PanelNode"): a stateful
# action needs get_values (so "configured" is decidable), summary_builder (or the
# summary line renders blank), and counts_as_setting=True (or the category badge
# ignores it). It touches no roles or channels, so it needs no
# requires_role_manage / required_channel_perms pre-check.

FREE_COLOR_NODE_KEY = "free_color_access"
FREE_COLOR_NODE_LABEL = "Free Color Access"
FREE_COLOR_NODE_DESCRIPTION = (
    "Let every member pick any embed color, instead of only the palettes their roles grant."
)


async def free_color_access_summary_values(guild_id: int) -> list:
    """Non-empty marker list when free color access is on.

    Drives the "configured" side of the Embed Settings progress badge.
    """
    try:
        if await EmbedConfigActions.get_free_color_access(guild_id):
            return ["free_color_access"]
    except Exception:
        logger.debug("free color access summary lookup failed", exc_info=True)
    return []


async def free_color_access_summary_text(guild_id: int) -> str:
    """One-line summary for the Embed Settings menu.

    The "off" state MUST return one of the engine's ``_UNSET_SUMMARIES`` strings
    or the category badge counts this node as configured on every guild. "Off"
    is not one of them, so the default state reads "Not set" - which is also
    honest here, since off means the admin has not opted into anything.
    """
    try:
        enabled = await EmbedConfigActions.get_free_color_access(guild_id)
    except Exception:
        logger.debug("free color access summary text failed", exc_info=True)
        return "Not set"
    return "On - any color allowed" if enabled else "Not set"


class _FreeColorAccessFlow(PanelFlow):
    """One admin's walk through the Free Color Access screen.

    Session binding, cooldown gating, notices and audit bookkeeping come from
    ``PanelFlow``; what is left here is the two screens.
    """

    node_key = FREE_COLOR_NODE_KEY
    audit_section = "embed_settings"

    async def start(self, interaction: discord.Interaction) -> None:
        await self._show_main(interaction)

    def _build_main_layout(self, enabled: bool) -> discord.ui.LayoutView:
        builder = AdminLayoutBuilder()
        builder.add_header(f"## {FREE_COLOR_NODE_LABEL}")

        if enabled:
            state = (
                "**Currently ON.** Every member can type any hex color when they "
                "build an embed. Members who also have color palettes from their "
                "roles can still pick from those."
            )
        else:
            state = (
                "**Currently OFF.** Embed colors follow the color sets assigned to "
                "each member's roles. A member with no palette assigned gets no "
                "color choice at all - their embeds use the server default color."
            )
        builder.add_item(readonly_container(discord.ui.TextDisplay(state)))

        if enabled:
            action_button = discord.ui.Button(
                label="Turn Off",
                style=discord.ButtonStyle.secondary,
                custom_id=cid("embed", "disable", FREE_COLOR_NODE_KEY),
            )
            action_button.callback = self._disable
        else:
            action_button = discord.ui.Button(
                label="Turn On",
                style=discord.ButtonStyle.primary,
                custom_id=cid("embed", "enable", FREE_COLOR_NODE_KEY),
            )
            action_button.callback = self._show_enable_confirm

        back_button = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            custom_id=cid("embed", "back", FREE_COLOR_NODE_KEY),
        )
        back_button.callback = self._back_to_parent

        builder.add_action_row(action_button, back_button)
        return builder.build()

    async def _show_main(self, interaction: discord.Interaction) -> None:
        enabled = await EmbedConfigActions.get_free_color_access(self.guild.id)
        await self._render(interaction, self._build_main_layout(enabled))

    async def _show_enable_confirm(self, interaction: discord.Interaction) -> None:
        """Enabling is the one direction that needs a deliberate confirmation."""
        layout = build_confirm_view(
            "Give every member free color access?",
            (
                "Turning this on lets **anyone** who can build an embed use **any** "
                "color, including colors you have not put in a palette. Your color "
                "sets and tier assignments stay exactly as they are, but they stop "
                "limiting anyone.\n\n"
                "You can turn this back off at any time."
            ),
            self._enable,
            self._show_main,
            confirm_label="Yes, allow any color",
            key=FREE_COLOR_NODE_KEY,
        )
        await self._render(interaction, layout)

    async def _enable(self, interaction: discord.Interaction) -> None:
        await self._set(interaction, True)

    async def _disable(self, interaction: discord.Interaction) -> None:
        await self._set(interaction, False)

    async def _set(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        previous = await EmbedConfigActions.get_free_color_access(self.guild.id)
        if not await EmbedConfigActions.set_free_color_access(self.guild.id, enabled):
            await self._notice(
                interaction, "Failed to Save",
                "Could not change free color access. Please try again.",
            )
            return

        await self._after_write(
            interaction, "enable" if enabled else "disable", previous, enabled,
        )
        logger.info(
            f"Free color access set to {enabled} in guild {self.guild.id} "
            f"by {interaction.user} ({interaction.user.id})"
        )
        await self._render(interaction, self._build_main_layout(enabled))


def build_free_color_access_node() -> PanelNode:
    """The ``action`` node behind Embed Settings -> Free Color Access."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _FreeColorAccessFlow(cog, guild, ctx, node).start(interaction)

    node = PanelNode(
        key=FREE_COLOR_NODE_KEY,
        label=FREE_COLOR_NODE_LABEL,
        kind="action",
        description=FREE_COLOR_NODE_DESCRIPTION,
        on_run=_on_run,
        get_values=free_color_access_summary_values,
        summary_builder=free_color_access_summary_text,
        # A real stored setting, not a one-shot action - count it in the badge.
        counts_as_setting=True,
    )
    return node
