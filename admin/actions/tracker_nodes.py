"""Tag Tracker and Boost Tracker admin-panel nodes.

Wires the two entries of the Trackers group to the views in ``admin/views/tracker_views.py``.
Before this module existed both were label-only ``_stub()`` PanelNodes, which made the whole
Trackers group a dead end in Discord: the views and the ``TrackerActions`` read/write layer
were written, but nothing connected them, so either entry rendered a description and a Back
button with no controls.

Both are single-screen flows (no sub-navigation), so each is one layout plus its handlers.
Shared session/cooldown/audit plumbing comes from ``PanelFlow``; see ``panel_flow.py``.

These two nodes opt into the engine's Discord-permission pre-checks
(``check_role_permissions`` / ``check_channel_permissions``), which the generic
``role_select`` / ``channel_select`` leaves get for free. Both features fail silently at
runtime without them: the Tag Tracker cannot assign a role that outranks the bot, and the
Boost Tracker cannot post to a channel it cannot see.
"""

from __future__ import annotations

import discord

from storage.log import get_logger
from ..permission_checks import check_channel_permissions, check_role_permissions
from ..views.panel_engine import ActionContext, PanelNode
from ..views.tracker_views import (
    NO_TAGS_TEXT,
    NO_WEARERS_TEXT,
    build_boost_tracker_settings_view,
    build_tag_tracker_settings_view,
)
from .panel_flow import PanelFlow
from .tracker_actions import TrackerActions

logger = get_logger("TrackerNodes")

# Permissions the bot needs in the boost log channel to actually log a boost.
#
# ``embed_links`` used to be on this list and was an over-ask: the only sender is
# ``Features/trackers/boosts/boost_tracker.py`` :365, a plain ``channel.send(message)``
# with a string and no embed. Asking for a permission the code never uses refuses
# channels the boost log would work perfectly well in, which is a wrong answer
# rather than a cautious one.
_BOOST_CHANNEL_PERMS = ["view_channel", "send_messages"]


# ── Tag Tracker ───────────────────────────────────────────────────────────────

async def tag_tracker_summary_values(guild_id: int) -> list:
    """Non-empty when Tag Tracker has something configured. Only the role counts:
    the tag text is filled in by the bot from members wearing it (2026-11-20), so
    it is not something an admin set."""
    try:
        s = await TrackerActions.get_tag_tracker_settings(guild_id)
    except Exception:
        logger.debug("tag_tracker summary lookup failed", exc_info=True)
        return []
    return ["role"] if s.get("tag_tracker_role_id") else []


async def tag_tracker_summary_text(guild_id: int) -> str:
    """One-line summary for the Trackers menu and the overview detail.

    An ``action`` node has no generic value the engine can render, so it supplies its
    own text. Returns an engine "unset" string when nothing is set, or the category
    badge would count it as configured.
    """
    try:
        s = await TrackerActions.get_tag_tracker_settings(guild_id)
    except Exception:
        logger.debug("tag_tracker summary text failed", exc_info=True)
        return "Not configured"

    tag = s.get("tag_tracker_server_tag")
    has_role = bool(s.get("tag_tracker_role_id"))
    if not has_role and not s.get("tag_tracker_enabled"):
        return "Not configured"

    state = "On" if s.get("tag_tracker_enabled") else "Off"
    parts = [state]
    parts.append(f"tag {tag}" if tag else "tag not seen yet")
    parts.append("role set" if has_role else "no role")
    return ", ".join(parts)


class _TagTrackerFlow(PanelFlow):
    node_key = "tag_tracker"
    audit_section = "trackers"

    async def _layout(self) -> discord.ui.LayoutView:
        settings = await TrackerActions.get_tag_tracker_settings(self.guild.id)
        tag, wearers = TrackerActions.detect_server_tag(self.guild)
        return build_tag_tracker_settings_view(
            settings=settings,
            guild=self.guild,
            available=TrackerActions.server_tags_available(self.guild),
            detected_tag=tag,
            wearers=wearers,
            on_toggle=self._toggle,
            on_role_select=self._select_role,
            on_refresh_tag=self._refresh_tag,
            on_cancel=self._back_to_parent,
        )

    async def start(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._layout())

    async def _toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        # Switching on needs a server that can have a tag at all, and a role to
        # hand out. The tag itself is not needed: members are matched by this
        # server's id, and its text is filled in from whoever wears it.
        if enabled:
            if not TrackerActions.server_tags_available(self.guild):
                await self._notice(interaction, "Server Tags Not Available", NO_TAGS_TEXT)
                return
            settings = await TrackerActions.get_tag_tracker_settings(self.guild.id)
            if not settings.get("tag_tracker_role_id"):
                await self._notice(
                    interaction, "Not Ready Yet",
                    "Pick the **tracked role** before switching Tag Tracker on. "
                    "It is the role members get while they wear this server's tag.",
                )
                return

        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return
        if not await TrackerActions.set_tag_tracker_enabled(self.guild.id, enabled):
            await self._failure_notice(
                interaction, "Failed to Save", "Could not change the Tag Tracker setting.",
            )
            return
        await self._after_write(interaction, "toggle", not enabled, enabled)
        await self._render(interaction, await self._layout())

    async def _select_role(self, interaction: discord.Interaction, role_id: int) -> None:
        ok, err = check_role_permissions(self.node, self.guild, role_id)
        if not ok:
            await self._notice(interaction, "Cannot Use That Role", err or "Please pick another role.")
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        old = (await TrackerActions.get_tag_tracker_settings(self.guild.id)).get("tag_tracker_role_id")
        if not await TrackerActions.set_tag_tracker_role(self.guild.id, role_id):
            await self._failure_notice(interaction, "Failed to Save", "Could not save that role.")
            return
        await self._after_write(interaction, "set", old, role_id)
        await self._render(interaction, await self._layout())

    async def _refresh_tag(self, interaction: discord.Interaction) -> None:
        """Re-read the tag text from members wearing it right now and save it.

        No network call: it reads the bot's member cache, so it answers inside
        the interaction window. The screen already shows the live reading; this
        button is for storing it straight away instead of at the next hourly
        sweep, so the dashboard shows it too."""
        tag, wearers = TrackerActions.detect_server_tag(self.guild)
        if not tag:
            await self._render(interaction, await self._layout())
            await self._notice(
                interaction, "Nobody Is Wearing It Yet",
                NO_WEARERS_TEXT if TrackerActions.server_tags_available(self.guild) else NO_TAGS_TEXT,
            )
            return
        old = (await TrackerActions.get_tag_tracker_settings(self.guild.id)).get("tag_tracker_server_tag")
        if old != tag:
            if not self._allowed(interaction):
                await self._too_fast(interaction)
                return
            if not await TrackerActions.set_tag_tracker_server_tag(self.guild.id, tag):
                await self._failure_notice(interaction, "Failed to Save", "Could not save the server tag.")
                return
            await self._after_write(interaction, "set", old, tag)
        await self._render(interaction, await self._layout())


def build_tag_tracker_node() -> PanelNode:
    """The ``action`` node behind Trackers -> Tag Tracker."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _TagTrackerFlow(cog, guild, ctx, node).start(interaction)

    node = PanelNode(
        key="tag_tracker",
        label="Tag Tracker",
        kind="action",
        description="Track members using the server tag and give them a role.",
        on_run=_on_run,
        get_values=tag_tracker_summary_values,
        summary_builder=tag_tracker_summary_text,
        counts_as_setting=True,
        requires_role_manage=True,
    )
    return node


# ── Boost Tracker ─────────────────────────────────────────────────────────────

async def boost_tracker_summary_values(guild_id: int) -> list:
    """Non-empty when a boost log channel is configured."""
    try:
        s = await TrackerActions.get_boost_tracker_settings(guild_id)
    except Exception:
        logger.debug("boost_tracker summary lookup failed", exc_info=True)
        return []
    channel_id = s.get("boost_log_channel_id")
    return [str(channel_id)] if channel_id else []


async def boost_tracker_summary_text(guild_id: int) -> str:
    """One-line summary for the Trackers menu and the overview detail."""
    try:
        s = await TrackerActions.get_boost_tracker_settings(guild_id)
    except Exception:
        logger.debug("boost_tracker summary text failed", exc_info=True)
        return "Not configured"

    channel_id = s.get("boost_log_channel_id")
    if not channel_id:
        return "Not configured"
    state = "On" if s.get("boost_enabled") else "Off"
    return f"{state}, <#{channel_id}>"


class _BoostTrackerFlow(PanelFlow):
    node_key = "boost_tracker"
    audit_section = "trackers"

    async def _layout(self) -> discord.ui.LayoutView:
        settings = await TrackerActions.get_boost_tracker_settings(self.guild.id)
        return build_boost_tracker_settings_view(
            settings=settings,
            guild=self.guild,
            on_toggle=self._toggle,
            on_channel_select=self._select_channel,
            on_cancel=self._back_to_parent,
        )

    async def start(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._layout())

    async def _toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        # With no log channel there is nowhere to write boost events, so enabling
        # would look like it worked and then do nothing.
        if enabled:
            settings = await TrackerActions.get_boost_tracker_settings(self.guild.id)
            if not settings.get("boost_log_channel_id"):
                await self._notice(
                    interaction, "Pick a Channel First",
                    "Choose a boost log channel below before switching Boost Tracker "
                    "on - otherwise there is nowhere for boost events to be posted.",
                )
                return

        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return
        if not await TrackerActions.set_boost_enabled(self.guild.id, enabled):
            await self._failure_notice(
                interaction, "Failed to Save", "Could not change the Boost Tracker setting.",
            )
            return
        await self._after_write(interaction, "toggle", not enabled, enabled)
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

        old = (await TrackerActions.get_boost_tracker_settings(self.guild.id)).get("boost_log_channel_id")
        if not await TrackerActions.set_boost_log_channel(self.guild.id, channel_id):
            await self._failure_notice(interaction, "Failed to Save", "Could not save that channel.")
            return
        await self._after_write(interaction, "set", old, channel_id)
        await self._render(interaction, await self._layout())


def build_boost_tracker_node() -> PanelNode:
    """The ``action`` node behind Trackers -> Boost Tracker."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _BoostTrackerFlow(cog, guild, ctx, node).start(interaction)

    node = PanelNode(
        key="boost_tracker",
        label="Boost Tracker",
        kind="action",
        description="Log server boosts to a channel.",
        on_run=_on_run,
        get_values=boost_tracker_summary_values,
        summary_builder=boost_tracker_summary_text,
        counts_as_setting=True,
        required_channel_perms=_BOOST_CHANNEL_PERMS,
    )
    return node
