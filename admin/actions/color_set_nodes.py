"""Color Tiers admin-panel node.

Wires the Color Set system into the ``color_tiers`` entry of the Embed Settings group.
Before this module existed, ``color_tiers`` was a label-only ``_stub()`` PanelNode: the
views in ``admin/views/color_views.py`` and the DB layer in ``color_set_actions.py`` were
both written, but nothing connected them, so opening Color Tiers rendered an empty screen.

Shape follows the suggestion nodes (``admin/bot_specific/codex/suggestions/``): an
``action``-kind node whose ``on_run`` drives a flow over message 2. The session binding,
cooldown gating, notices and audit bookkeeping come from ``PanelFlow``
(``panel_flow.py``); what is left here is the Color Set screens themselves.

Navigation map (all in-place edits of message 2):

    Embed Settings -> Color Tiers
      |
      +- (no default color yet) Setup Required -> set default color -> seeds defaults
      |
      +- Color Sets menu
           +- Create Color Set (modal)
           +- Change Default Color (modal)
           +- <a set> -> set detail
                          +- Add Colors (modal)
                          +- Remove a color / Remove an assignment
                          +- Assign to Tier / Assign to Role
                          +- Delete Set -> confirm

Modal submits respond with UPDATE_MESSAGE (``modal_interaction.response.edit_message``),
which Discord permits because every modal here is opened from a component on message 2.
That keeps the re-render on the modal's own interaction rather than reaching back to the
component interaction whose response was already consumed by ``send_modal``.
"""

from __future__ import annotations

import discord

from storage.log import get_logger
from ..views.panel_engine import PanelNode, ActionContext
from ..views.base import build_notice_layout
from ..views.color_views import (
    TIER_LABELS,
    ColorAddModal,
    ColorSetCreateModal,
    DefaultColorModal,
    build_color_set_detail,
    build_color_sets_menu,
    build_default_color_setup_view,
    build_delete_confirm_view,
    build_role_assign_view,
    build_tier_assign_view,
)
from .color_set_actions import ColorSetActions
from .panel_flow import PanelFlow

from Features.ce_utilities.color_normalizer import (
    color_int_to_hex,
    normalize_color,
    parse_named_colors_string,
)

logger = get_logger("ColorTiersNode")

NODE_KEY = "color_tiers"
NODE_LABEL = "Color Tiers"
NODE_DESCRIPTION = "Manage per-guild color palettes."

# Every color set must keep at least one color; an empty set would appear in the
# member-facing picker with nothing to pick.
_MIN_COLORS_PER_SET = 1


async def color_tiers_summary_values(guild_id: int) -> list:
    """Return a non-empty marker list when Color Tiers is configured.

    Considered configured if a server default color is set OR any color sets exist.
    Drives the "configured" side of the parent menu's progress badge via
    ``PanelNode.get_values``; the human-readable text comes from
    ``color_tiers_summary_text`` below.
    """
    out: list = []
    try:
        if await ColorSetActions.get_default_color(guild_id) is not None:
            out.append("default_color")
    except Exception:
        logger.debug("color_tiers summary: default color lookup failed", exc_info=True)
    try:
        sets = await ColorSetActions.list_color_sets(guild_id)
        if sets:
            out.append(f"sets:{len(sets)}")
    except Exception:
        logger.debug("color_tiers summary: set listing failed", exc_info=True)
    return out


async def color_tiers_summary_text(guild_id: int) -> str:
    """One-line summary for the Embed Settings menu and the overview detail.

    An ``action`` node has no generic value the engine can render, so it supplies its
    own text via ``PanelNode.summary_builder``. Must return one of the engine's
    "unset" strings when nothing is configured, or the category badge counts it as done.
    """
    try:
        default_color = await ColorSetActions.get_default_color(guild_id)
        sets = await ColorSetActions.list_color_sets(guild_id)
    except Exception:
        logger.debug("color_tiers summary text failed", exc_info=True)
        return "Not configured"

    if default_color is None and not sets:
        return "Not configured"
    parts = []
    if default_color is not None:
        parts.append(f"default {color_int_to_hex(default_color)}")
    parts.append(f"{len(sets)} set(s)" if sets else "no sets yet")
    return ", ".join(parts)


class _ColorTiersFlow(PanelFlow):
    """One admin's walk through the Color Tiers screens.

    Instantiated per ``on_run``, so the "currently open set" lives on the instance
    instead of being threaded through every callback signature. Session binding,
    cooldowns, notices and audit bookkeeping come from ``PanelFlow``.
    """

    node_key = NODE_KEY
    audit_section = "embed_settings"

    def __init__(self, cog, guild: discord.Guild, ctx: ActionContext, node: PanelNode):
        super().__init__(cog, guild, ctx, node)
        self.set_id: str | None = None

    async def _stale(self, interaction: discord.Interaction, title: str, body: str) -> None:
        """Refresh whichever screen is current, then explain what changed."""
        await self._refresh_then_notice(
            interaction, title, body, await self._detail_or_menu_layout(),
        )

    # -- entry point --------------------------------------------------------

    async def start(self, interaction: discord.Interaction) -> None:
        """Open Color Tiers: force default-color setup first, else show the menu."""
        if await ColorSetActions.get_default_color(self.guild.id) is None:
            await self._render(interaction, self._setup_layout())
            return
        await ColorSetActions.ensure_seeded(self.guild.id)
        await self._render(interaction, await self._menu_layout())

    # -- first-run setup ----------------------------------------------------

    def _setup_layout(self) -> discord.ui.LayoutView:
        return build_default_color_setup_view(
            on_set_default=self._open_default_modal,
            on_back=self._back_to_parent,
        )

    async def _open_default_modal(self, interaction: discord.Interaction) -> None:
        current = await ColorSetActions.get_default_color(self.guild.id)
        first_run = current is None
        await interaction.response.send_modal(DefaultColorModal(
            callback=self._submit_default_color(first_run),
            title="Set Default Color" if first_run else "Change Default Color",
            current_hex="" if first_run else color_int_to_hex(current),
        ))

    def _submit_default_color(self, first_run: bool):
        async def _submit(interaction: discord.Interaction, raw: str) -> None:
            color = normalize_color(raw)
            if color is None:
                await self._notice(
                    interaction, "Invalid Color",
                    f"Could not read `{raw}` as a color. Use a hex code like `#FF0000` "
                    "or an rgb value like `rgb(255, 0, 0)`.",
                )
                return
            if not self._allowed(interaction):
                await self._too_fast(interaction)
                return

            old = await ColorSetActions.get_default_color(self.guild.id)
            if not await ColorSetActions.set_default_color(self.guild.id, color):
                await self._notice(
                    interaction, "Failed to Save", "Could not save the default color.",
                )
                return
            await self._after_write(
                interaction, "set",
                color_int_to_hex(old) if old is not None else None,
                color_int_to_hex(color),
            )

            # First run: the forced-setup gate is now satisfied, so stock the guild
            # with the starter palettes before showing the menu.
            if first_run:
                created = await ColorSetActions.ensure_seeded(self.guild.id)
                if created:
                    logger.info(
                        f"Seeded {created} default color sets for guild {self.guild.id} "
                        f"on first Color Tiers open"
                    )
            await self._render_via_modal(interaction, await self._menu_layout())

        return _submit

    # -- top-level menu -----------------------------------------------------

    async def _menu_layout(self) -> discord.ui.LayoutView:
        sets = await ColorSetActions.list_color_sets(self.guild.id)
        assignments = await ColorSetActions.list_assignments(self.guild.id)
        default_color = await ColorSetActions.get_default_color(self.guild.id)

        counts: dict[str, int] = {}
        tier_per_set: dict[str, str | None] = {}
        for a in assignments:
            sid = a["color_set_id"]
            counts[sid] = counts.get(sid, 0) + 1
            if a["target_type"] == "tier":
                tier_per_set[sid] = a["target_id"]

        return build_color_sets_menu(
            sets=sets,
            assignment_counts=counts,
            default_color=default_color or 0,
            tier_per_set=tier_per_set,
            on_create=self._open_create_modal,
            on_select_set=self._open_set,
            on_change_default=self._open_default_modal,
            on_cancel=self._back_to_parent,
        )

    async def _show_menu(self, interaction: discord.Interaction) -> None:
        self.set_id = None
        await self._render(interaction, await self._menu_layout())

    async def _open_create_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ColorSetCreateModal(callback=self._submit_create))

    async def _submit_create(self, interaction: discord.Interaction, name: str, raw_colors: str) -> None:
        colors, failed = parse_named_colors_string(raw_colors)
        if not colors:
            await self._notice(
                interaction, "No Valid Colors",
                "None of those lines were readable. Use one color per line as "
                "`Name: #RRGGBB` or `Name: rgb(r, g, b)`.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        set_id = await ColorSetActions.create_color_set(self.guild.id, name, "", colors)
        if not set_id:
            await self._notice(interaction, "Failed to Save", f"Could not create **{name}**.")
            return
        await self._after_write(interaction, "create", None, f"{name} ({len(colors)} colors)")

        self.set_id = set_id
        await self._render_via_modal(interaction, await self._detail_or_menu_layout())
        if failed:
            await interaction.followup.send(
                view=build_notice_layout(
                    "Some Lines Skipped",
                    f"Created **{name}** with {len(colors)} color(s). "
                    f"These lines could not be read:\n"
                    + "\n".join(f"- `{line}`" for line in failed[:10]),
                ),
                ephemeral=True,
            )

    # -- set detail ---------------------------------------------------------

    async def _detail_layout(self) -> discord.ui.LayoutView | None:
        """Build the detail view for self.set_id, or None if the set is gone."""
        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            return None
        assignments = await ColorSetActions.list_assignments(self.guild.id, set_id=self.set_id)
        return build_color_set_detail(
            color_set=color_set,
            assignments=assignments,
            guild=self.guild,
            on_add_colors=self._open_add_colors_modal,
            on_remove_color=self._remove_color,
            on_remove_assignment=self._remove_assignment,
            on_assign_role=self._show_role_assign,
            on_assign_tier=self._show_tier_assign,
            on_delete_set=self._show_delete_confirm,
            on_back=self._show_menu,
        )

    async def _detail_or_menu_layout(self) -> discord.ui.LayoutView:
        """The detail view when the open set still exists, else the top-level menu."""
        layout = await self._detail_layout() if self.set_id else None
        if layout is None:
            self.set_id = None
            return await self._menu_layout()
        return layout

    async def _show_detail(self, interaction: discord.Interaction) -> None:
        layout = await self._detail_layout()
        if layout is None:
            await self._show_gone(interaction)
            return
        await self._render(interaction, layout)

    async def _show_gone(self, interaction: discord.Interaction) -> None:
        """The open set vanished (deleted elsewhere) - fall back to the menu."""
        self.set_id = None
        await self._stale(
            interaction, "Set Not Found",
            "That color set no longer exists. Showing the current list.",
        )

    async def _open_set(self, interaction: discord.Interaction, set_id: str) -> None:
        self.set_id = set_id
        await self._show_detail(interaction)

    async def _open_add_colors_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ColorAddModal(callback=self._submit_add_colors))

    async def _submit_add_colors(self, interaction: discord.Interaction, raw_colors: str) -> None:
        new_colors, failed = parse_named_colors_string(raw_colors)
        if not new_colors:
            await self._notice(
                interaction, "No Valid Colors",
                "None of those lines were readable. Use one color per line as "
                "`Name: #RRGGBB` or `Name: rgb(r, g, b)`.",
            )
            return

        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            await self._notice(
                interaction, "Set Not Found", "That color set no longer exists.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        existing = color_set.get("colors", [])
        seen = {c["value"] for c in existing}
        added = [c for c in new_colors if c["value"] not in seen]
        if not added:
            await self._notice(
                interaction, "Already Present",
                f"**{color_set['name']}** already has every one of those colors.",
            )
            return

        if not await ColorSetActions.update_color_set_colors(
            self.guild.id, self.set_id, existing + added,
        ):
            await self._notice(interaction, "Failed to Save", "Could not add those colors.")
            return
        await self._after_write(interaction, "update", len(existing), len(existing) + len(added))

        await self._render_via_modal(interaction, await self._detail_or_menu_layout())
        skipped = len(new_colors) - len(added)
        if failed or skipped:
            parts = []
            if skipped:
                parts.append(f"{skipped} color(s) were already in the set.")
            if failed:
                parts.append(
                    "These lines could not be read:\n"
                    + "\n".join(f"- `{line}`" for line in failed[:10])
                )
            await interaction.followup.send(
                view=build_notice_layout(
                    "Added with Notes",
                    f"Added {len(added)} color(s). " + " ".join(parts),
                ),
                ephemeral=True,
            )

    async def _remove_color(self, interaction: discord.Interaction, index: int) -> None:
        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            await self._show_gone(interaction)
            return

        colors = color_set.get("colors", [])
        if not 0 <= index < len(colors):
            await self._stale(
                interaction, "Color Not Found",
                "That color is no longer in this set. Showing the current list.",
            )
            return
        if len(colors) - 1 < _MIN_COLORS_PER_SET:
            await self._notice(
                interaction, "Cannot Remove",
                f"**{color_set['name']}** must keep at least one color. Delete the "
                "whole set instead if you no longer need it.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        removed = colors[index]
        remaining = colors[:index] + colors[index + 1:]
        if not await ColorSetActions.update_color_set_colors(
            self.guild.id, self.set_id, remaining,
        ):
            await self._notice(interaction, "Failed to Save", "Could not remove that color.")
            return
        await self._after_write(
            interaction, "remove",
            removed.get("name") or color_int_to_hex(removed["value"]),
            None,
        )
        await self._show_detail(interaction)

    async def _remove_assignment(self, interaction: discord.Interaction, assignment_id: str) -> None:
        # The detail view identifies assignments by assignment_id, but the delete
        # action keys on (target_type, target_id) - resolve one to the other.
        assignments = await ColorSetActions.list_assignments(self.guild.id, set_id=self.set_id)
        match = next((a for a in assignments if a["assignment_id"] == assignment_id), None)
        if match is None:
            await self._stale(
                interaction, "Assignment Not Found",
                "That assignment has already been removed.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        if not await ColorSetActions.delete_assignment(
            self.guild.id, self.set_id, match["target_type"], match["target_id"],
        ):
            await self._notice(
                interaction, "Failed to Save", "Could not remove that assignment.",
            )
            return
        await self._after_write(
            interaction, "remove", f"{match['target_type']}:{match['target_id']}", None,
        )
        await self._show_detail(interaction)

    # -- assignment flows ---------------------------------------------------

    async def _show_role_assign(self, interaction: discord.Interaction) -> None:
        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            await self._show_gone(interaction)
            return
        await self._render(interaction, build_role_assign_view(
            color_set_name=color_set["name"],
            on_role_selected=self._assign_role,
            on_back=self._show_detail,
        ))

    async def _assign_role(self, interaction: discord.Interaction, role_id: int) -> None:
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return
        if not await ColorSetActions.upsert_assignment(
            self.guild.id, self.set_id, "role", str(role_id),
        ):
            await self._notice(
                interaction, "Failed to Save", "Could not assign that role.",
            )
            return
        await self._after_write(interaction, "assign", None, f"role:{role_id}")
        await self._show_detail(interaction)

    async def _show_tier_assign(self, interaction: discord.Interaction) -> None:
        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            await self._show_gone(interaction)
            return
        await self._render(interaction, build_tier_assign_view(
            color_set_name=color_set["name"],
            on_tier_selected=self._assign_tier,
            on_back=self._show_detail,
        ))

    async def _assign_tier(self, interaction: discord.Interaction, tier: str) -> None:
        # A set may hold at most one tier assignment (the view says so); enforce it
        # here rather than silently ending up with two.
        assignments = await ColorSetActions.list_assignments(self.guild.id, set_id=self.set_id)
        existing_tier = next((a for a in assignments if a["target_type"] == "tier"), None)
        if existing_tier is not None and existing_tier["target_id"] != tier:
            current = TIER_LABELS.get(existing_tier["target_id"], existing_tier["target_id"])
            await self._notice(
                interaction, "Already Assigned to a Tier",
                f"This set is assigned to **{current}**. Remove that assignment "
                "first, then assign it to a different tier.",
            )
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        if not await ColorSetActions.upsert_assignment(
            self.guild.id, self.set_id, "tier", tier,
        ):
            await self._notice(
                interaction, "Failed to Save", "Could not assign that tier.",
            )
            return
        await self._after_write(interaction, "assign", None, f"tier:{tier}")
        await self._show_detail(interaction)

    # -- deletion -----------------------------------------------------------

    async def _show_delete_confirm(self, interaction: discord.Interaction) -> None:
        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            await self._show_gone(interaction)
            return
        await self._render(interaction, build_delete_confirm_view(
            set_name=color_set["name"],
            on_confirm=self._delete_set,
            on_cancel=self._show_detail,
        ))

    async def _delete_set(self, interaction: discord.Interaction) -> None:
        color_set = await ColorSetActions.get_color_set(self.guild.id, self.set_id)
        if color_set is None:
            await self._show_gone(interaction)
            return
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        name = color_set["name"]
        if not await ColorSetActions.delete_color_set(self.guild.id, self.set_id):
            await self._notice(interaction, "Failed to Delete", f"Could not delete **{name}**.")
            return
        await self._after_write(interaction, "delete", name, None)
        await self._show_menu(interaction)


def build_color_tiers_node() -> PanelNode:
    """The ``action`` node behind Embed Settings -> Color Tiers."""

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _ColorTiersFlow(cog, guild, ctx, node).start(interaction)

    node = PanelNode(
        key=NODE_KEY,
        label=NODE_LABEL,
        kind="action",
        description=NODE_DESCRIPTION,
        on_run=_on_run,
        get_values=color_tiers_summary_values,
        summary_builder=color_tiers_summary_text,
        # A bespoke settings editor, not a one-shot action - count it in the badge.
        counts_as_setting=True,
    )
    return node
