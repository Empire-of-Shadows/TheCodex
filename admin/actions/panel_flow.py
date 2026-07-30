"""Shared plumbing for bespoke ``action``-node flows.

Codex has several admin-panel entries whose UI does not fit the engine's generic leaf
contract (``get_values`` / ``set_values`` over a single value), so they are ``action``
nodes driven by a hand-written flow: Color Tiers, Tag Tracker, Boost Tracker. Every one
of those needs the same six pieces of bookkeeping, and getting any of them wrong is a
subtle, user-visible bug:

* render into message 2 **while keeping the view bound to the panel session** - a freshly
  built LayoutView otherwise loses the author lock and runs on its own 300s timeout
  instead of the session's shared idle timer;
* respond exactly once per interaction (Discord allows one response, then followups);
* gate repeat writes behind the cog's autosave cooldown;
* invalidate the guild's caches after a write;
* record the write in the audit log against the admin who made it;
* refresh the message-1 overview so its summary line stops being stale.

``PanelFlow`` holds that plumbing so each feature flow only contains its own screens.
Subclasses set ``node_key`` (the cooldown / rate-limit key) and ``audit_section`` (the
section label used in audit entries), then implement their screens on top.
"""

from __future__ import annotations

import discord

from storage.log import get_logger
from ..views.base import AdminLayoutBuilder, build_notice_layout
from ..views.panel_engine import ActionContext, PanelNode

logger = get_logger("PanelFlow")


class PanelFlow:
    """Base for a bespoke action-node flow. See module docstring."""

    #: Cooldown / rate-limit key; also the label used when logging.
    node_key: str = "panel_flow"
    #: Section recorded on audit entries for writes made through this flow.
    audit_section: str = ""

    def __init__(self, cog, guild: discord.Guild, ctx: ActionContext, node: PanelNode):
        self.cog = cog
        self.guild = guild
        self.ctx = ctx
        self.node = node

    # -- rendering ----------------------------------------------------------

    async def _render(self, interaction: discord.Interaction, layout: discord.ui.LayoutView) -> None:
        """Show a layout on message 2, keeping it bound to the panel session.

        Works whether or not the interaction has already been responded to: after a
        ``defer()`` the engine's ``_send_or_edit`` edits the original response instead
        of trying to respond twice.
        """
        bound = self.cog._rebind_session_view(self.ctx.session, layout)
        await self.cog._send_or_edit(interaction, bound, True)

    async def _render_via_modal(
        self, interaction: discord.Interaction, layout: discord.ui.LayoutView,
    ) -> None:
        """Re-render message 2 from a modal-submit interaction (UPDATE_MESSAGE).

        Valid because every modal in these flows is opened from a component sitting on
        message 2, so Discord accepts an update-message response to the submit.
        """
        bound = self.cog._rebind_session_view(self.ctx.session, layout)
        try:
            await interaction.response.edit_message(view=bound)
        except discord.HTTPException as exc:
            logger.warning("Could not refresh %s after modal submit: %s", self.node_key, exc)

    # -- responses ----------------------------------------------------------

    async def _notice(self, interaction: discord.Interaction, title: str, body: str) -> None:
        """Send an ephemeral notice, as a response or a followup as appropriate."""
        view = build_notice_layout(title, body)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(view=view, ephemeral=True)
            else:
                await interaction.response.send_message(view=view, ephemeral=True)
        except discord.HTTPException as exc:
            logger.warning("Could not deliver %s notice: %s", self.node_key, exc)

    async def _refresh_then_notice(
        self, interaction: discord.Interaction, title: str, body: str,
        layout: discord.ui.LayoutView,
    ) -> None:
        """Re-render, then explain - for acting on data that has since changed.

        An interaction takes only one response, so the response goes to the refresh
        (which is what the admin needs to see) and the explanation follows up.
        """
        await self._render(interaction, layout)
        await self._notice(interaction, title, body)

    # -- write gating & bookkeeping -----------------------------------------

    def _allowed(self, interaction: discord.Interaction) -> bool:
        """Whether this admin may write again yet (autosave cooldown)."""
        return self.cog._check_cooldown(interaction.user.id, self.node_key, self.guild.id)

    async def _too_fast(self, interaction: discord.Interaction) -> None:
        await self._notice(
            interaction, "Slow Down", "Please wait a moment before trying again.",
        )

    async def _after_write(
        self, interaction: discord.Interaction, action: str, old_value, new_value,
    ) -> None:
        """Post-write bookkeeping: caches, audit trail, message-1 summary."""
        self.cog._invalidate_guild_caches(self.guild.id)
        await self.cog._audit(
            interaction, self.guild.id, self.node,
            old_value=old_value, new_value=new_value,
            action=action, section=self.audit_section or None,
        )
        if self.ctx.refresh_parent:
            await self.ctx.refresh_parent()

    # -- navigation ---------------------------------------------------------

    async def _back_to_parent(self, interaction: discord.Interaction) -> None:
        """Return to the group menu this node was opened from."""
        if self.ctx.parent_node is not None:
            await self.cog._navigate_to(
                interaction, self.ctx.parent_node, self.guild,
                parent_node=self.ctx.grandparent_node, edit=True,
                refresh_parent=self.ctx.refresh_parent, session=self.ctx.session,
            )
        else:
            await interaction.response.edit_message(
                view=AdminLayoutBuilder().add_text("Closed.").build()
            )
