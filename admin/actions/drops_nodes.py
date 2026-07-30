"""Drops Channel and Tracked Channels admin-panel nodes.

Wires two of the three dead entries in the Updates & Drops group to the views in
``admin/views/drops_views.py``. Both were label-only ``_stub()`` PanelNodes, so picking
either one rendered a description and a Back button with no controls even though the views
and the ``DropsActions`` read/write layer were both already written.

The third dead entry, ``drops_manager_role``, needs no module of its own: it is a plain
single-role setting, so ``panel_configs.py`` builds it with the engine's ``role_leaf``
factory straight onto the ``drops.manager_role_id`` config path.

Shared session/cooldown/audit plumbing comes from ``PanelFlow``; see ``panel_flow.py``.

Note ``drops_manager_role`` deliberately does NOT set ``requires_role_manage``: the bot only
ever *checks* whether a member holds that role (``DropsActions.has_drops_management``), it
never assigns it, so it does not need Manage Roles or to outrank it. The drops posting
channel does declare ``required_channel_perms`` - the daily post fails silently otherwise.
"""

from __future__ import annotations

import discord

from storage.log import get_logger
from ..permission_checks import check_channel_permissions
from ..views.drops_views import (
    TRACKER_CATEGORIES,
    build_drops_channel_view,
    build_drops_tracker_view,
)
from ..views.panel_engine import ActionContext, PanelNode
from .drops_actions import DropsActions
from .panel_flow import PanelFlow

logger = get_logger("DropsNodes")

# Permissions the bot needs in the drops posting channel to publish the daily post.
DROPS_CHANNEL_PERMS = ["view_channel", "send_messages", "embed_links"]

# Tracked channels are only read for statistics, so the bot just needs to see them.
_TRACKER_CHANNEL_PERMS = ["view_channel", "read_message_history"]


# ── Drops Channel ─────────────────────────────────────────────────────────────

async def drops_channel_summary_values(guild_id: int) -> list:
    """Non-empty when a drops posting channel is configured."""
    try:
        s = await DropsActions.get_drops_settings(guild_id)
    except Exception:
        logger.debug("drops_channel summary lookup failed", exc_info=True)
        return []
    channel_id = s.get("drops_channel_id")
    return [str(channel_id)] if channel_id else []


class _DropsChannelFlow(PanelFlow):
    node_key = "drops_channel"
    audit_section = "updates_drops"

    async def _layout(self) -> discord.ui.LayoutView:
        settings = await DropsActions.get_drops_settings(self.guild.id)
        return build_drops_channel_view(
            settings=settings,
            guild=self.guild,
            on_channel_select=self._select_channel,
            on_cancel=self._back_to_parent,
            on_toggle=self._toggle,
        )

    async def start(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._layout())

    async def _select_channel(self, interaction: discord.Interaction, channel_id: int) -> None:
        ok, err = check_channel_permissions(self.node, self.guild, channel_id)
        if not ok:
            await self._notice(
                interaction, "Cannot Use That Channel", err or "Please pick another channel.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        old = (await DropsActions.get_drops_settings(self.guild.id)).get("drops_channel_id")
        if not await DropsActions.set_drops_channel(self.guild.id, channel_id):
            await self._notice(interaction, "Failed to Save", "Could not save that channel.")
            return
        await self._after_write(interaction, "set", old, channel_id)
        await self._render(interaction, await self._layout())

    async def _toggle(self, interaction: discord.Interaction) -> None:
        """Flip the drops feature on/off.

        The view only renders this button once a channel is set, but re-check here so a
        stale view cannot enable a feature that has nowhere to post.
        """
        settings = await DropsActions.get_drops_settings(self.guild.id)
        enabled = bool(settings.get("drops_enabled", False))
        if not enabled and not settings.get("drops_channel_id"):
            await self._notice(
                interaction, "Pick a Channel First",
                "Choose a drops posting channel before switching Updates & Drops on - "
                "otherwise the daily post has nowhere to go.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        if not await DropsActions.set_enabled(self.guild.id, not enabled):
            await self._notice(
                interaction, "Failed to Save", "Could not change the Updates & Drops setting.",
            )
            return
        await self._after_write(interaction, "toggle", enabled, not enabled)
        await self._render(interaction, await self._layout())


def build_drops_channel_node() -> PanelNode:
    """The ``action`` node behind Updates & Drops -> Drops Channel."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _DropsChannelFlow(cog, guild, ctx, node).start(interaction)

    node = PanelNode(
        key="drops_channel",
        label="Drops Channel",
        kind="action",
        description="Channel for daily Prime Gaming drops posts.",
        on_run=_on_run,
        get_values=drops_channel_summary_values,
        required_channel_perms=DROPS_CHANNEL_PERMS,
        mod_allowed=False,
    )
    return node


# ── Tracked Channels ──────────────────────────────────────────────────────────

async def drops_tracker_summary_values(guild_id: int) -> list:
    """One entry per tracked category that has a channel set."""
    try:
        s = await DropsActions.get_drops_settings(guild_id)
    except Exception:
        logger.debug("drops_tracker summary lookup failed", exc_info=True)
        return []
    tracked = s.get("drops_tracker_channels") or {}
    return [cat for cat in TRACKER_CATEGORIES if tracked.get(cat)]


class _DropsTrackerFlow(PanelFlow):
    node_key = "drops_tracker"
    audit_section = "updates_drops"

    async def _layout(self) -> discord.ui.LayoutView:
        settings = await DropsActions.get_drops_settings(self.guild.id)
        return build_drops_tracker_view(
            settings=settings,
            guild=self.guild,
            on_channel_select=self._set_category,
            on_remove=self._clear_category,
            on_cancel=self._back_to_parent,
        )

    async def start(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._layout())

    async def _set_category(
        self, interaction: discord.Interaction, category: str, channel_id: int,
    ) -> None:
        if category not in TRACKER_CATEGORIES:
            await self._notice(
                interaction, "Unknown Category", f"`{category}` is not a tracked category.",
            )
            return

        # Tracked channels are read for stats, so the bot needs to see their history.
        ok, err = check_channel_permissions(_TRACKER_PERM_NODE, self.guild, channel_id)
        if not ok:
            await self._notice(
                interaction, "Cannot Track That Channel", err or "Please pick another channel.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        settings = await DropsActions.get_drops_settings(self.guild.id)
        old = (settings.get("drops_tracker_channels") or {}).get(category)
        if not await DropsActions.set_tracker_channel(self.guild.id, category, channel_id):
            await self._notice(interaction, "Failed to Save", f"Could not set the {category} channel.")
            return
        await self._after_write(interaction, "set", f"{category}:{old}", f"{category}:{channel_id}")
        await self._render(interaction, await self._layout())

    async def _clear_category(self, interaction: discord.Interaction, category: str) -> None:
        if category not in TRACKER_CATEGORIES:
            await self._notice(
                interaction, "Unknown Category", f"`{category}` is not a tracked category.",
            )
            return

        settings = await DropsActions.get_drops_settings(self.guild.id)
        old = (settings.get("drops_tracker_channels") or {}).get(category)
        if not old:
            await self._refresh_then_notice(
                interaction, "Nothing to Clear",
                f"**{category}** does not have a channel set. Showing the current list.",
                await self._layout(),
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        if not await DropsActions.remove_tracker_channel(self.guild.id, category):
            await self._notice(
                interaction, "Failed to Save", f"Could not clear the {category} channel.",
            )
            return
        await self._after_write(interaction, "clear", f"{category}:{old}", None)
        await self._render(interaction, await self._layout())


def build_drops_tracker_node() -> PanelNode:
    """The ``action`` node behind Updates & Drops -> Tracked Channels."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _DropsTrackerFlow(cog, guild, ctx, node).start(interaction)

    node = PanelNode(
        key="drops_tracker",
        label="Tracked Channels",
        kind="action",
        description="Channels watched for drops statistics.",
        on_run=_on_run,
        get_values=drops_tracker_summary_values,
        mod_allowed=False,
    )
    return node


# Permission-check carrier for the tracked-channel selects. `check_channel_permissions`
# reads its requirement list off a PanelNode, and the tracker node itself needs a
# different (read-only) set than the posting channel, so hand it a node declaring those.
_TRACKER_PERM_NODE = PanelNode(
    key="drops_tracker",
    label="Tracked Channels",
    kind="action",
    required_channel_perms=_TRACKER_CHANNEL_PERMS,
)
