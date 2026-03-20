"""
Admin Panel Engine — Generic config-driven panel builder.

Defines PanelNode dataclass and generic view builders (build_menu_view,
build_select_view) so new admin panels can be added as pure config trees
without writing custom view builder code.
"""

from __future__ import annotations

import discord
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional

from .base import AdminLayoutBuilder, create_unique_id, create_empty_layout


@dataclass
class PanelNode:
    """A node in the admin panel config tree.

    Attributes:
        key:          Unique identifier; also used as rate-limit cooldown key.
        label:        Display label for headers and dropdown options.
        kind:         Node type: "menu" | "role_select" | "channel_select" | "option_select"
        description:  Short description shown in the parent dropdown and as
                      instruction text on the select view.

        children:     (menu only) Ordered dict of child_key → PanelNode.
        get_values:   async (guild_id) → list  — returns the current selection.
        set_values:   async (guild_id, values) → bool  — persists new selection.
        clear_values: Optional async (guild_id) → bool  — enables a Clear button.
        options:      (option_select only) list of (value, label) or
                      (value, label, description) tuples.
        min_values:   Minimum number of selections (default 1).
        max_values:   Maximum number of selections (default 25).
    """

    key: str
    label: str
    kind: str  # "menu" | "role_select" | "channel_select" | "option_select" | "modal_input"
    description: str = ""

    # menu nodes only
    children: dict[str, "PanelNode"] = field(default_factory=dict)

    # select / modal_input nodes
    get_values: Optional[Callable] = None   # async (guild_id) → list[int | str]
    set_values: Optional[Callable] = None   # async (guild_id, values) → bool
    clear_values: Optional[Callable] = None  # async (guild_id) → bool
    pre_check: Optional[Callable] = None       # async (interaction, guild_id) → Embed|None; None=allow, Embed=block+notify
    post_save_hook: Optional[Callable] = None  # async (interaction, guild_id, saved_values) → None; runs after successful save

    # option_select only
    options: Optional[list] = None          # [(val, label[, desc]), ...]
    min_values: int = 1
    max_values: int = 25

    # modal_input only
    modal_title: str = ""           # Modal window title
    modal_label: str = "Value"      # Text input label
    modal_placeholder: str = ""     # Input placeholder text
    modal_min_length: int = 1       # Minimum input length
    modal_max_length: int = 100     # Maximum input length
    modal_validator: Optional[Callable] = None  # (str) → (bool, converted_value, error_msg)
    modal_paragraph: bool = False   # Use paragraph (multiline) text style
    modal_required: bool = True     # Whether the field is required in Discord modal

    # file_upload only
    schema_validator: Optional[Callable] = None  # (data) → (bool, error_msg)

    # dual_modal_input — second field
    modal_label_2: str = ""
    modal_placeholder_2: str = ""
    modal_min_length_2: int = 0
    modal_max_length_2: int = 500


# ── Helpers ──────────────────────────────────────────────────────────────────

def _child_summary(kind: str, values: list) -> str:
    """Return a short human-readable summary of a child node's current value."""
    n = len(values)
    if kind == "role_select":
        return f"{n} role(s) assigned" if n else "Not assigned"
    if kind == "channel_select":
        return "Channel configured" if n else "Not set"
    if kind == "option_select":
        if not n:
            return "Not set"
        return str(values[0]) if n == 1 else f"{n} selected"
    if kind == "modal_input":
        return str(values[0]) if values else "Not set"
    if kind == "file_upload":
        return "Custom JSON active" if values else "Default layout"
    if kind == "dual_modal_input":
        val1 = values[0] if len(values) > 0 else ""
        return str(val1) if val1 else "Not set"
    if kind == "menu":
        return f"{n} items configured" if n else "Not configured"
    return f"{n} configured" if n else "Not set"


# ── Generic view builders ─────────────────────────────────────────────────────

def build_menu_view(
    node: PanelNode,
    summary_map: dict[str, list],
    on_select: Callable[[discord.Interaction, str], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build an overview menu view for a PanelNode with kind="menu".

    Args:
        node:        The menu PanelNode to render.
        summary_map: Pre-fetched {child_key: current_values_list} for all children.
        on_select:   Async callback (interaction, child_key) — navigate into child.
        on_cancel:   Async callback (interaction) — close / Done.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {node.label}")

    if node.description:
        builder.add_text(node.description)
        builder.add_separator()

    # Summary lines for each child
    lines = [
        f"- **{child.label}:** {_child_summary(child.kind, summary_map.get(key, []))}"
        for key, child in node.children.items()
    ]
    if lines:
        builder.add_text("\n".join(lines))

    builder.add_separator()
    builder.add_text("Select a category below to configure it.")

    options = [
        discord.SelectOption(
            label=child.label,
            value=key,
            description=_child_summary(child.kind, summary_map.get(key, [])),
        )
        for key, child in node.children.items()
    ]
    select = discord.ui.Select(
        placeholder="Select a category...",
        custom_id=f"menu_select_{unique_id}",
        options=options,
    )

    async def _select_cb(interaction: discord.Interaction):
        await on_select(interaction, interaction.data["values"][0])

    select.callback = _select_cb
    builder.add_select(select)

    done_btn = discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.secondary,
        custom_id=f"done_{unique_id}",
    )
    done_btn.callback = on_cancel
    row = discord.ui.ActionRow()
    row.add_item(done_btn)
    builder.add_item(row)

    return builder.build()


def build_select_view(
    node: PanelNode,
    current_values: list,
    guild: discord.Guild,
    on_save: Callable[[discord.Interaction, list], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    on_clear: Optional[Callable[[discord.Interaction], Awaitable[None]]] = None,
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """Build a select view for a PanelNode with kind in (role_select, channel_select, option_select).

    The component auto-saves on change (no explicit Save button); Back navigates
    to the parent; Clear (if provided) removes all values.

    Args:
        node:           The select PanelNode to render.
        current_values: Pre-fetched list of current values (role IDs, channel IDs, or option strings).
        guild:          The Discord guild, used to resolve role/channel names.
        on_save:        Async callback (interaction, values) — called immediately when the
                        select component fires.
        on_back:        Async callback (interaction) — navigate back to parent menu.
        on_clear:       Optional async callback (interaction) — clear all values.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {node.label}")

    # Current value display
    if node.kind == "role_select":
        if current_values:
            names = []
            for rid in current_values:
                role = guild.get_role(int(rid))
                names.append(role.name if role else f"Unknown ({rid})")
            builder.add_text(f"**Currently assigned:** {', '.join(names)}")
        else:
            builder.add_text("*No roles currently assigned.*")

    elif node.kind == "channel_select":
        if current_values:
            ch = guild.get_channel(int(current_values[0]))
            builder.add_text(f"**Current channel:** {ch.mention if ch else f'Unknown ({current_values[0]})'}")
        else:
            builder.add_text("*No channel currently set.*")

    elif node.kind == "option_select":
        if current_values:
            opt_label_map = {str(opt[0]): opt[1] for opt in (node.options or [])}
            names = [opt_label_map.get(str(v), str(v)) for v in current_values]
            builder.add_text(f"**Currently selected:** {', '.join(names)}")
        else:
            builder.add_text("*Nothing currently selected.*")

    builder.add_separator()
    builder.add_text(node.description or f"Select values for **{node.label}**.")

    # Build the select component
    if node.kind == "role_select":
        component = discord.ui.RoleSelect(
            placeholder=f"Select roles for {node.label}...",
            custom_id=f"select_{unique_id}",
            min_values=node.min_values,
            max_values=node.max_values,
            default_values=[discord.Object(id=int(rid)) for rid in current_values],
        )

        async def _role_cb(interaction: discord.Interaction):
            role_ids = [int(rid) for rid in interaction.data.get("resolved", {}).get("roles", {}).keys()]
            await on_save(interaction, role_ids)

        component.callback = _role_cb

    elif node.kind == "channel_select":
        component = discord.ui.ChannelSelect(
            placeholder=f"Select channel for {node.label}...",
            custom_id=f"select_{unique_id}",
            min_values=node.min_values,
            max_values=node.max_values,
            default_values=[discord.Object(id=int(v)) for v in current_values],
        )

        async def _channel_cb(interaction: discord.Interaction):
            channel_ids = [int(cid) for cid in interaction.data.get("values", [])]
            await on_save(interaction, channel_ids)

        component.callback = _channel_cb

    elif node.kind == "option_select":
        current_strs = [str(v) for v in current_values]
        option_objects = []
        for opt in (node.options or []):
            val, lbl = str(opt[0]), opt[1]
            desc = opt[2] if len(opt) > 2 else None
            option_objects.append(
                discord.SelectOption(
                    label=lbl,
                    value=val,
                    description=desc,
                    default=(val in current_strs),
                )
            )
        component = discord.ui.Select(
            placeholder=f"Select one or more options...",
            custom_id=f"select_{unique_id}",
            min_values=node.min_values,
            max_values=min(node.max_values, len(option_objects)) if option_objects else 1,
            options=option_objects,
        )

        async def _option_cb(interaction: discord.Interaction):
            await on_save(interaction, interaction.data["values"])

        component.callback = _option_cb

    else:
        return create_empty_layout(f"Unknown node kind: {node.kind!r}")

    builder.add_select(component)

    # Back + optional Clear row
    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=f"back_{unique_id}",
    )
    back_btn.callback = on_back
    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=f"clear_{unique_id}",
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        btn_row.add_item(clear_btn)

    builder.add_item(btn_row)

    return builder.build()


# ── Modal input support ───────────────────────────────────────────────────────

class PanelInputModal(discord.ui.Modal):
    """Generic single-field modal used by build_modal_trigger_view."""

    def __init__(
        self,
        *,
        title: str,
        label: str,
        placeholder: str,
        min_length: int,
        max_length: int,
        default: str,
        on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]],
        paragraph: bool = False,
        required: bool = True,
    ):
        super().__init__(title=title)
        self._callback = on_submit_callback
        self.value_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder or None,
            required=required,
            style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
            min_length=min_length,
            max_length=max_length,
            default=default or None,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self._callback(interaction, self.value_input.value.strip())


def build_modal_trigger_view(
    node: PanelNode,
    current_values: list,
    guild: discord.Guild,
    on_save: Callable[[discord.Interaction, discord.Interaction, str], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    on_clear: Optional[Callable[[discord.Interaction], Awaitable[None]]] = None,
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """Build a trigger view for a PanelNode with kind="modal_input".

    Shows the current value and a button that opens a modal for editing.
    on_save receives (button_interaction, modal_interaction, raw_value).
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {node.label}")

    if current_values:
        builder.add_text(f"**Current value:** {current_values[0]}")
    else:
        builder.add_text("*Not currently set.*")

    builder.add_separator()
    builder.add_text(node.description or f"Set a value for **{node.label}**.")

    set_btn = discord.ui.Button(
        label=f"Set {node.label}",
        style=discord.ButtonStyle.primary,
        custom_id=f"set_{unique_id}",
    )

    async def set_btn_callback(bi: discord.Interaction):
        async def _on_submit(mi: discord.Interaction, raw: str):
            await on_save(bi, mi, raw)

        modal = PanelInputModal(
            title=node.modal_title or f"Set {node.label}",
            label=node.modal_label or "Value",
            placeholder=node.modal_placeholder or "",
            min_length=node.modal_min_length,
            max_length=node.modal_max_length,
            default=current_values[0] if current_values else "",
            on_submit_callback=_on_submit,
            paragraph=node.modal_paragraph,
            required=node.modal_required,
        )
        await bi.response.send_modal(modal)

    set_btn.callback = set_btn_callback

    action_items = [set_btn]
    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=f"clear_{unique_id}",
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        action_items.append(clear_btn)

    builder.add_action_row(*action_items)

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=f"back_{unique_id}",
    )
    back_btn.callback = on_back
    back_row = discord.ui.ActionRow()
    back_row.add_item(back_btn)
    builder.add_item(back_row)

    return builder.build()


# ── Dual-field modal input support ───────────────────────────────────────────

class _PanelDualInputModal(discord.ui.Modal):
    """Two-field modal used by build_dual_modal_trigger_view."""

    def __init__(
        self,
        *,
        title: str,
        label: str,
        placeholder: str,
        min_length: int,
        max_length: int,
        default: str,
        label_2: str,
        placeholder_2: str,
        min_length_2: int,
        max_length_2: int,
        default_2: str,
        on_submit_callback: Callable[[discord.Interaction, str, str], Awaitable[None]],
    ):
        super().__init__(title=title)
        self._callback = on_submit_callback
        self.value_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder or None,
            required=True,
            style=discord.TextStyle.short,
            min_length=min_length,
            max_length=max_length,
            default=default or None,
        )
        self.value_input_2 = discord.ui.TextInput(
            label=label_2,
            placeholder=placeholder_2 or None,
            required=False,
            style=discord.TextStyle.paragraph,
            min_length=min_length_2,
            max_length=max_length_2,
            default=default_2 or None,
        )
        self.add_item(self.value_input)
        self.add_item(self.value_input_2)

    async def on_submit(self, interaction: discord.Interaction):
        await self._callback(
            interaction,
            self.value_input.value.strip(),
            self.value_input_2.value.strip(),
        )


def build_dual_modal_trigger_view(
    node: PanelNode,
    current_values: list,
    guild: discord.Guild,
    on_save: Callable[[discord.Interaction, discord.Interaction, str, str], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """Build a trigger view for a PanelNode with kind="dual_modal_input".

    Shows both current values and a button that opens a two-field modal.
    on_save receives (button_interaction, modal_interaction, val1, val2).
    current_values is expected to be a 2-element list [field_1, field_2].
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {node.label}")

    val1 = current_values[0] if len(current_values) > 0 else ""
    val2 = current_values[1] if len(current_values) > 1 else ""

    if val1 or val2:
        lines = []
        if val1:
            lines.append(f"**{node.modal_label or 'Field 1'}:** {val1}")
        if val2:
            lines.append(f"**{node.modal_label_2 or 'Field 2'}:** {val2}")
        builder.add_text("\n".join(lines))
    else:
        builder.add_text("*Not currently set.*")

    builder.add_separator()
    builder.add_text(node.description or f"Set values for **{node.label}**.")

    edit_btn = discord.ui.Button(
        label="Edit",
        style=discord.ButtonStyle.primary,
        custom_id=f"edit_{unique_id}",
    )

    async def edit_btn_callback(bi: discord.Interaction):
        async def _on_submit(mi: discord.Interaction, raw1: str, raw2: str):
            await on_save(bi, mi, raw1, raw2)

        modal = _PanelDualInputModal(
            title=node.modal_title or f"Set {node.label}",
            label=node.modal_label or "Field 1",
            placeholder=node.modal_placeholder or "",
            min_length=node.modal_min_length,
            max_length=node.modal_max_length,
            default=val1,
            label_2=node.modal_label_2 or "Field 2",
            placeholder_2=node.modal_placeholder_2 or "",
            min_length_2=node.modal_min_length_2,
            max_length_2=node.modal_max_length_2,
            default_2=val2,
            on_submit_callback=_on_submit,
        )
        await bi.response.send_modal(modal)

    edit_btn.callback = edit_btn_callback
    builder.add_action_row(edit_btn)

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=f"back_{unique_id}",
    )
    back_btn.callback = on_back
    back_row = discord.ui.ActionRow()
    back_row.add_item(back_btn)
    builder.add_item(back_row)

    return builder.build()


# ── File upload modal + status view ──────────────────────────────────────────

class PanelFileUploadModal(discord.ui.Modal):
    """Modal with a single file upload field for panel file_upload nodes."""

    upload_label = discord.ui.Label(
        text="JSON File",
        component=discord.ui.FileUpload(
            custom_id="panel_file_upload",
            min_values=1,
            max_values=1,
        ),
    )

    def __init__(self, *, title: str, on_submit_callback: Callable):
        super().__init__(title=title)
        self._callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        await self._callback(interaction, self.upload_label.component.values[0])


def build_file_upload_status_view(
    node: PanelNode,
    current_values: list,
    guild: discord.Guild,
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    on_clear: Optional[Callable[[discord.Interaction], Awaitable[None]]] = None,
    back_label: str = "Back",
    on_upload: Optional[Callable] = None,
) -> discord.ui.LayoutView:
    """Build a status view for a PanelNode with kind="file_upload".

    Shows whether a custom JSON layout is active and provides Upload / Clear / Back buttons.

    Args:
        node:           The file_upload PanelNode to render.
        current_values: List with one element (raw JSON string) if active, else empty.
        guild:          The Discord guild.
        on_back:        Async callback (interaction) — navigate back to parent menu.
        on_clear:       Optional async callback (interaction) — clear the stored JSON.
        back_label:     Label for the back button ("Back" or "Close").
        on_upload:      Optional async (button_interaction, modal_interaction, attachment) — called on file submit.
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {node.label}")

    if current_values:
        builder.add_text("**Custom JSON:** ✅ Active")
    else:
        builder.add_text("**Custom JSON:** ⬜ Not set — using default layout")

    builder.add_separator()

    if node.description:
        builder.add_text(node.description)

    btn_row = discord.ui.ActionRow()

    if on_upload is not None:
        upload_btn = discord.ui.Button(
            label="Upload JSON",
            style=discord.ButtonStyle.primary,
            custom_id=f"upload_{unique_id}",
        )

        async def upload_btn_cb(bi: discord.Interaction):
            async def _on_submit(mi, attachment):
                await on_upload(bi, mi, attachment)

            modal = PanelFileUploadModal(
                title=f"Upload {node.label}",
                on_submit_callback=_on_submit,
            )
            await bi.response.send_modal(modal)

        upload_btn.callback = upload_btn_cb
        btn_row.add_item(upload_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=f"clear_{unique_id}",
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        btn_row.add_item(clear_btn)

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=f"back_{unique_id}",
    )
    back_btn.callback = on_back
    btn_row.add_item(back_btn)

    builder.add_item(btn_row)

    return builder.build()
