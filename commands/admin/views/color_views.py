"""
Color Set Panel Views — Discord Components v2 LayoutViews.

Provides all view builders and modals for the Color Set admin panel:
  - build_color_sets_menu      → top-level list/create
  - build_color_set_detail     → per-set detail with actions
  - build_role_assign_view     → pick role → save immediately
  - build_tier_assign_view     → pick tier via dropdown → save immediately
  - build_delete_confirm_view  → confirm permanent deletion
  - ColorSetCreateModal        → create a new set (name + colors)
  - ColorAddModal              → add colors to an existing set
"""

from __future__ import annotations

from typing import Callable, Awaitable, Optional

import discord

from .base import create_unique_id, AdminLayoutBuilder, create_empty_layout
from Features.ce_utilities.color_normalizer import color_int_to_hex


# ── Constants ──────────────────────────────────────────────────────────────────

# Tier targets matching embed_views.TIER_NAMES
TIER_NAMES = ["tier_1", "tier_2", "tier_3", "tier_4", "tier_5"]
TIER_LABELS = {
    "tier_1": "Tier 1",
    "tier_2": "Tier 2",
    "tier_3": "Tier 3",
    "tier_4": "Tier 4",
    "tier_5": "Tier 5",
}


# ── Modals ─────────────────────────────────────────────────────────────────────

class DefaultColorModal(discord.ui.Modal):
    """Modal to set or change the server default color (one color, always available to all members)."""

    color_input = discord.ui.TextInput(
        label="Default Color",
        placeholder="e.g. #FF0000, red, rgb(0, 170, 255)",
        required=True,
        max_length=50,
    )

    def __init__(
        self,
        callback: Callable[[discord.Interaction, str], Awaitable[None]],
        *,
        title: str = "Set Default Color",
        current_hex: str = "",
    ):
        super().__init__(title=title)
        self._callback = callback
        if current_hex:
            self.color_input.default = current_hex

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, self.color_input.value.strip())


class ColorSetCreateModal(discord.ui.Modal, title="Create Color Set"):
    """Modal to create a new color set (name + initial named colors)."""

    name_input = discord.ui.TextInput(
        label="Set Name",
        placeholder="e.g. Premium Colors, Staff Palette",
        required=True,
        max_length=50,
    )
    colors_input = discord.ui.TextInput(
        label="Colors (one per line: Name: #HEX or rgb())",
        placeholder="Crimson Red: #DC143C\nOcean Blue: rgb(0, 100, 200)\nGold: #FFD700",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, callback: Callable[[discord.Interaction, str, str], Awaitable[None]]):
        super().__init__()
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(
            interaction,
            self.name_input.value.strip(),
            self.colors_input.value.strip(),
        )


class ColorAddModal(discord.ui.Modal, title="Add Colors"):
    """Modal to add more named colors to an existing color set."""

    colors_input = discord.ui.TextInput(
        label="Colors (one per line: Name: #HEX or rgb())",
        placeholder="Crimson Red: #DC143C\nOcean Blue: rgb(0, 100, 200)",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, callback: Callable[[discord.Interaction, str], Awaitable[None]]):
        super().__init__()
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, self.colors_input.value.strip())


# ── View builders ──────────────────────────────────────────────────────────────

def build_default_color_setup_view(
    on_set_default: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Forced first-time setup view shown before any Color Tier settings are accessible.

    Args:
        on_set_default: Opens the DefaultColorModal to capture the color.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header("## Color Tiers — Setup Required")
    builder.add_text(
        "Before managing Color Tiers, you must set a **server default color**.\n\n"
        "This is a base color that **every member** always has access to, "
        "regardless of their tier or role assignments. Think of it as your server's theme color.\n\n"
        "You can change it at any time from the Color Tiers menu."
    )
    builder.add_separator()

    set_btn = discord.ui.Button(
        label="Set Default Color",
        style=discord.ButtonStyle.green,
        custom_id=f"cs_setdefault_{unique_id}",
    )
    set_btn.callback = on_set_default
    builder.add_action_row(set_btn)

    return builder.build()


def build_color_sets_menu(
    sets: list[dict],
    assignment_counts: dict[str, int],
    default_color: int,
    tier_per_set: dict[str, str | None],
    on_create: Callable[[discord.Interaction], Awaitable[None]],
    on_select_set: Callable[[discord.Interaction, str], Awaitable[None]],
    on_change_default: Callable[[discord.Interaction], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the top-level Color Sets menu.

    Args:
        sets:               List of color set dicts from ColorSetActions.
        assignment_counts:  {set_id: count} pre-computed assignment counts.
        default_color:      Server default color int (always available to all members).
        tier_per_set:       {set_id: tier_name | None} — the tier each set is assigned to.
        on_create:          Callback for the "Create Color Set" button.
        on_select_set:      Async callback (interaction, set_id) when a set is selected.
        on_change_default:  Callback to open the change-default-color modal.
        on_cancel:          Callback for the "Done" button.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header("## Color Sets")
    builder.add_text(
        f"**Server Default Color:** `{color_int_to_hex(default_color)}` "
        f"*(available to all members)*"
    )

    if sets:
        lines = []
        for s in sets:
            color_count = len(s.get("colors", []))
            assign_count = assignment_counts.get(s["set_id"], 0)
            tier = tier_per_set.get(s["set_id"])
            if tier:
                tier_badge = f" · **{TIER_LABELS.get(tier, tier)}**"
            elif assign_count > 0:
                tier_badge = " · Role only"
            else:
                tier_badge = " · Unassigned"
            lines.append(
                f"- **{s['name']}** — {color_count} color(s){tier_badge}"
            )
        builder.add_text("\n".join(lines))
    else:
        builder.add_text("*No color sets configured yet.*")

    builder.add_separator()
    builder.add_text("Select a set to configure, or create a new one.")

    if sets:
        options = [
            discord.SelectOption(
                label=s["name"],
                value=s["set_id"],
                description=(
                    f"{len(s.get('colors', []))} colors · "
                    f"{assignment_counts.get(s['set_id'], 0)} assignments"
                )[:100],
            )
            for s in sets[:25]
        ]
        select = discord.ui.Select(
            placeholder="Select a color set...",
            custom_id=f"cs_select_{unique_id}",
            options=options,
        )

        async def _select_cb(interaction: discord.Interaction) -> None:
            await on_select_set(interaction, interaction.data["values"][0])

        select.callback = _select_cb
        builder.add_select(select)

    create_btn = discord.ui.Button(
        label="Create Color Set",
        style=discord.ButtonStyle.green,
        custom_id=f"cs_create_{unique_id}",
    )
    create_btn.callback = on_create

    change_default_btn = discord.ui.Button(
        label="Change Default Color",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_chgdefault_{unique_id}",
    )
    change_default_btn.callback = on_change_default

    done_btn = discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_done_{unique_id}",
    )
    done_btn.callback = on_cancel

    builder.add_action_row(create_btn, change_default_btn, done_btn)

    return builder.build()


def build_color_set_detail(
    color_set: dict,
    assignments: list[dict],
    guild: discord.Guild,
    on_add_colors: Callable[[discord.Interaction], Awaitable[None]],
    on_remove_color: Callable[[discord.Interaction, int], Awaitable[None]],
    on_remove_assignment: Callable[[discord.Interaction, str], Awaitable[None]],
    on_assign_role: Callable[[discord.Interaction], Awaitable[None]],
    on_assign_tier: Callable[[discord.Interaction], Awaitable[None]],
    on_delete_set: Callable[[discord.Interaction], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the detail view for a single color set.

    Args:
        color_set:            Color set dict from ColorSetActions.
        assignments:          Assignments for this specific set.
        guild:                Discord guild (for resolving role names).
        on_add_colors:        Opens the add-colors modal.
        on_remove_color:      Callback (interaction, color_index) when a color is chosen for removal.
        on_remove_assignment: Callback (interaction, assignment_id) when an assignment is removed.
        on_assign_role:       Opens the role assign flow.
        on_assign_tier:       Opens the tier assign flow.
        on_delete_set:        Triggers deletion confirmation.
        on_back:              Returns to the menu.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    set_name = color_set.get("name", "Unknown")
    colors: list[int] = color_set.get("colors", [])

    builder.add_header(f"## {set_name}")

    # Colors display
    if colors:
        color_lines = []
        for c in colors[:20]:
            name = c.get("name", "")
            hex_str = color_int_to_hex(c["value"])
            color_lines.append(f"- **{name}** `{hex_str}`" if name else f"- `{hex_str}`")
        suffix = f"\n- *+{len(colors) - 20} more*" if len(colors) > 20 else ""
        builder.add_text("**Colors:**\n" + "\n".join(color_lines) + suffix)
    else:
        builder.add_text("*No colors in this set yet.*")

    # Assignments display (no mode column — always additive)
    if assignments:
        assign_lines = []
        for a in assignments:
            t_type = a.get("target_type", "?")
            t_id = a.get("target_id", "?")

            if t_type == "role":
                role = guild.get_role(int(t_id)) if t_id.isdigit() else None
                label = f"@{role.name}" if role else f"role:{t_id}"
                badge = "role"
            else:
                label = TIER_LABELS.get(t_id, t_id)
                badge = "tier"

            assign_lines.append(f"- **{label}** [{badge}]")

        builder.add_text("**Assignments:**\n" + "\n".join(assign_lines))
    else:
        builder.add_text("*No assignments yet.*")

    builder.add_separator()

    # Remove color select (only if there are colors)
    if colors:
        remove_options = [
            discord.SelectOption(
                label=(f"{c['name']} ({color_int_to_hex(c['value'])})"
                       if c.get("name") else color_int_to_hex(c["value"]))[:100],
                value=str(i),  # index-based — unambiguous even with duplicate values
                description=f"Remove {color_int_to_hex(c['value'])} from this set",
            )
            for i, c in enumerate(colors[:25])
        ]
        remove_select = discord.ui.Select(
            placeholder="Remove a color...",
            custom_id=f"cs_remove_{unique_id}",
            options=remove_options,
        )

        async def _remove_cb(interaction: discord.Interaction) -> None:
            await on_remove_color(interaction, int(interaction.data["values"][0]))

        remove_select.callback = _remove_cb
        builder.add_select(remove_select)

    # Remove assignment select (only if there are assignments)
    if assignments:
        def _assignment_label(a: dict) -> str:
            t_type = a.get("target_type", "?")
            t_id = a.get("target_id", "?")
            if t_type == "role":
                role = guild.get_role(int(t_id)) if t_id.isdigit() else None
                target = f"@{role.name}" if role else f"role:{t_id}"
                badge = "role"
            else:
                target = TIER_LABELS.get(t_id, t_id)
                badge = "tier"
            return f"{target} [{badge}]"[:100]

        rm_assign_options = [
            discord.SelectOption(
                label=_assignment_label(a),
                value=a["assignment_id"],
                description="Remove this assignment",
            )
            for a in assignments[:25]
        ]
        rm_assign_select = discord.ui.Select(
            placeholder="Remove an assignment...",
            custom_id=f"cs_rma_{unique_id}",
            options=rm_assign_options,
        )

        async def _remove_assign_cb(interaction: discord.Interaction) -> None:
            await on_remove_assignment(interaction, interaction.data["values"][0])

        rm_assign_select.callback = _remove_assign_cb
        builder.add_select(rm_assign_select)

    # Assignment hint
    builder.add_text(
        "-# **Assign to Tier** - normal access for all members of a tier.\n"
        "-# **Assign to Role** - privilege override for specific roles (e.g. mods, admins)."
    )

    # Action row: Assign to Tier | Assign to Role | Add Colors | Delete | Back
    assign_tier_btn = discord.ui.Button(
        label="Assign to Tier",
        style=discord.ButtonStyle.primary,
        custom_id=f"cs_tier_{unique_id}",
    )
    assign_tier_btn.callback = on_assign_tier

    assign_role_btn = discord.ui.Button(
        label="Assign to Role",
        style=discord.ButtonStyle.primary,
        custom_id=f"cs_role_{unique_id}",
    )
    assign_role_btn.callback = on_assign_role

    add_colors_btn = discord.ui.Button(
        label="Add Colors",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_add_{unique_id}",
    )
    add_colors_btn.callback = on_add_colors

    delete_btn = discord.ui.Button(
        label="Delete Set",
        style=discord.ButtonStyle.danger,
        custom_id=f"cs_del_{unique_id}",
    )
    delete_btn.callback = on_delete_set

    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_back_{unique_id}",
    )
    back_btn.callback = on_back

    builder.add_action_row(assign_tier_btn, assign_role_btn, add_colors_btn, delete_btn, back_btn)

    return builder.build()


def build_role_assign_view(
    color_set_name: str,
    on_role_selected: Callable[[discord.Interaction, int], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the role assignment view: choose a role → save immediately.

    Args:
        color_set_name:   Display name of the set being assigned.
        on_role_selected: Callback (interaction, role_id) when a role is chosen.
        on_back:          Returns to the detail view.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## Assign to Role — {color_set_name}")
    builder.add_text(
        "**This is a privilege override.** Use this to grant specific roles — such as moderators, "
        "admins, or other privileged members — direct access to this color set, bypassing the tier "
        "system entirely.\n\n"
        "Members with the selected role will have access to all colors in this set in addition to "
        "any colors they already receive from their tier."
    )
    builder.add_separator()

    role_select = discord.ui.RoleSelect(
        placeholder="Select a role to assign this set to...",
        custom_id=f"cs_rolesel_{unique_id}",
        min_values=1,
        max_values=1,
    )

    async def _role_cb(interaction: discord.Interaction) -> None:
        role_ids = list(interaction.data.get("resolved", {}).get("roles", {}).keys())
        if role_ids:
            await on_role_selected(interaction, int(role_ids[0]))

    role_select.callback = _role_cb
    builder.add_select(role_select)

    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_back_{unique_id}",
    )
    back_btn.callback = on_back
    builder.add_action_row(back_btn)

    return builder.build()


def build_tier_assign_view(
    color_set_name: str,
    on_tier_selected: Callable[[discord.Interaction, str], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the tier assignment view: choose a tier → save immediately.

    A color set can be assigned to at most one tier. Attempting to assign
    to a second tier is blocked with an error.

    Args:
        color_set_name:   Display name of the set being assigned.
        on_tier_selected: Callback (interaction, tier_key) when a tier is chosen.
        on_back:          Returns to the detail view.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## Assign to Tier — {color_set_name}")
    builder.add_text(
        "Select a tier below. All members whose roles map to this tier will gain "
        "access to the colors in this set.\n\n"
        "**Note:** A color set can only be assigned to one tier. To change tiers, "
        "remove the existing tier assignment first."
    )
    builder.add_separator()

    options = [
        discord.SelectOption(
            label=TIER_LABELS[tier],
            value=tier,
            description=f"Assign this color set to {TIER_LABELS[tier]}",
        )
        for tier in TIER_NAMES
    ]
    tier_select = discord.ui.Select(
        placeholder="Select a tier...",
        custom_id=f"cs_tiersel_{unique_id}",
        options=options,
        min_values=1,
        max_values=1,
    )

    async def _tier_cb(interaction: discord.Interaction) -> None:
        await on_tier_selected(interaction, interaction.data["values"][0])

    tier_select.callback = _tier_cb
    builder.add_select(tier_select)

    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_back_{unique_id}",
    )
    back_btn.callback = on_back
    builder.add_action_row(back_btn)

    return builder.build()


def build_delete_confirm_view(
    set_name: str,
    on_confirm: Callable[[discord.Interaction], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the delete confirmation view for a color set.

    Args:
        set_name:   The name of the set to be deleted.
        on_confirm: Proceed with the deletion.
        on_cancel:  Abort and return to the detail view.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header("## Confirm Deletion")
    builder.add_text(
        f"This will permanently delete **{set_name}** and all its assignments.\n\n"
        "This action cannot be undone."
    )
    builder.add_separator()

    confirm_btn = discord.ui.Button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        custom_id=f"cs_confirm_{unique_id}",
    )
    confirm_btn.callback = on_confirm

    cancel_btn = discord.ui.Button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id=f"cs_cfcancel_{unique_id}",
    )
    cancel_btn.callback = on_cancel

    builder.add_action_row(confirm_btn, cancel_btn)

    return builder.build()
