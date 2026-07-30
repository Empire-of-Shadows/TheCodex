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
    TagTrackerServerTagModal,
    build_boost_tracker_settings_view,
    build_tag_tracker_settings_view,
)
from .panel_flow import PanelFlow
from .tracker_actions import TrackerActions

logger = get_logger("TrackerNodes")

# Permissions the bot needs in the boost log channel to actually log a boost.
_BOOST_CHANNEL_PERMS = ["view_channel", "send_messages", "embed_links"]


# ── Tag Tracker ───────────────────────────────────────────────────────────────

async def tag_tracker_summary_values(guild_id: int) -> list:
    """Non-empty when Tag Tracker has something configured (role and/or tag)."""
    try:
        s = await TrackerActions.get_tag_tracker_settings(guild_id)
    except Exception:
        logger.debug("tag_tracker summary lookup failed", exc_info=True)
        return []
    out = []
    if s.get("tag_tracker_role_id"):
        out.append("role")
    if s.get("tag_tracker_server_tag"):
        out.append("tag")
    return out


class _TagTrackerFlow(PanelFlow):
    node_key = "tag_tracker"
    audit_section = "trackers"

    async def _layout(self) -> discord.ui.LayoutView:
        settings = await TrackerActions.get_tag_tracker_settings(self.guild.id)
        return build_tag_tracker_settings_view(
            settings=settings,
            guild=self.guild,
            on_toggle=self._toggle,
            on_role_select=self._select_role,
            on_edit_tag=self._open_tag_modal,
            on_detect_tag=self._detect_tag,
            on_cancel=self._back_to_parent,
        )

    async def start(self, interaction: discord.Interaction) -> None:
        await self._render(interaction, await self._layout())

    async def _toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        # Turning the tracker on without a role or tag would leave it running with
        # nothing to match, so require both first.
        if enabled:
            settings = await TrackerActions.get_tag_tracker_settings(self.guild.id)
            missing = []
            if not settings.get("tag_tracker_role_id"):
                missing.append("a **tracked role**")
            if not settings.get("tag_tracker_server_tag"):
                missing.append("a **server tag**")
            if missing:
                await self._notice(
                    interaction, "Not Ready Yet",
                    "Set " + " and ".join(missing) + " before switching Tag Tracker on. "
                    "Without both it has nothing to match members against.",
                )
                return

        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return
        if not await TrackerActions.set_tag_tracker_enabled(self.guild.id, enabled):
            await self._notice(
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
            await self._notice(interaction, "Failed to Save", "Could not save that role.")
            return
        await self._after_write(interaction, "set", old, role_id)
        await self._render(interaction, await self._layout())

    async def _open_tag_modal(self, interaction: discord.Interaction) -> None:
        settings = await TrackerActions.get_tag_tracker_settings(self.guild.id)
        await interaction.response.send_modal(TagTrackerServerTagModal(
            callback=self._submit_tag,
            current_tag=settings.get("tag_tracker_server_tag") or "",
        ))

    async def _submit_tag(self, interaction: discord.Interaction, tag: str) -> None:
        if not tag:
            await self._notice(
                interaction, "Empty Tag", "Enter the server tag you want to track.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        old = (await TrackerActions.get_tag_tracker_settings(self.guild.id)).get("tag_tracker_server_tag")
        if not await TrackerActions.set_tag_tracker_server_tag(self.guild.id, tag):
            await self._notice(interaction, "Failed to Save", "Could not save that server tag.")
            return
        await self._after_write(interaction, "set", old, tag)
        await self._render_via_modal(interaction, await self._layout())

    async def _detect_tag(self, interaction: discord.Interaction) -> None:
        # Fetching from Discord is network I/O, so defer first rather than risk
        # blowing the 3-second interaction response window.
        try:
            await interaction.response.defer()
        except discord.HTTPException as exc:
            logger.warning("Could not defer tag detection: %s", exc)
            return

        tag = await TrackerActions.fetch_server_tag(self.cog.bot, self.guild.id)
        if not tag:
            await self._render(interaction, await self._layout())
            await self._notice(
                interaction, "No Server Tag Found",
                "This server does not have a tag set on Discord's side, so there is "
                "nothing to detect. Set one in Server Settings, or use **Edit Server "
                "Tag** to type it in manually.",
            )
            return

        settings = await TrackerActions.get_tag_tracker_settings(self.guild.id)
        old = settings.get("tag_tracker_server_tag")
        if old == tag:
            await self._render(interaction, await self._layout())
            await self._notice(
                interaction, "Already Up To Date",
                f"This server's tag is `{tag}`, which is what Tag Tracker is already using.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        if not await TrackerActions.set_tag_tracker_server_tag(self.guild.id, tag):
            await self._notice(interaction, "Failed to Save", "Could not save the detected tag.")
            return
        await self._after_write(interaction, "set", old, tag)
        await self._render(interaction, await self._layout())
        await self._notice(
            interaction, "Server Tag Detected", f"Tag Tracker is now matching `{tag}`.",
        )


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
        requires_role_manage=True,
        mod_allowed=False,
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
            await self._notice(
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
            await self._notice(interaction, "Failed to Save", "Could not save that channel.")
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
        required_channel_perms=_BOOST_CHANNEL_PERMS,
        mod_allowed=False,
    )
    return node
