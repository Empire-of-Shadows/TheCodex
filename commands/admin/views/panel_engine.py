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

from .base import (
    AdminLayoutBuilder,
    cid,
    create_empty_layout,
    readonly_container,
    editable_container,
    notice_container,
)


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
    kind: str  # "menu" | "role_select" | "channel_select" | "option_select" | "modal_input" | "dual_modal_input" | "file_upload" | "dict_editor"
    description: str = ""

    # menu nodes only
    children: dict[str, "PanelNode"] = field(default_factory=dict)

    # menu lock / toggle support (TheHost parity per ADMIN_PANEL_STANDARD.md)
    locked_children: Optional[Callable] = None  # async (guild_id) -> set[str]
    lock_reason: str = ""
    toggle_get: Optional[Callable] = None       # async (guild_id) -> bool
    toggle_set: Optional[Callable] = None       # async (guild_id, bool) -> bool
    on_toggle_callback: Optional[Callable] = None
    description_builder: Optional[Callable] = None  # sync (guild_id) -> str; overrides static description at render time

    # select / modal_input nodes
    get_values: Optional[Callable] = None   # async (guild_id) → list[int | str]
    set_values: Optional[Callable] = None   # async (guild_id, values) → bool
    clear_values: Optional[Callable] = None  # async (guild_id) → bool
    pre_check: Optional[Callable] = None       # async (interaction, guild_id) → LayoutView|None; None=allow
    post_save_hook: Optional[Callable] = None  # async (interaction, guild_id, saved_values) → None

    # channel_select only
    channel_types: Optional[list] = None   # list[discord.ChannelType] to filter

    # option_select only
    options: Optional[list] = None          # [(val, label[, desc]), ...]
    min_values: int = 1
    max_values: int = 25

    # premium gating (scaffolding for cross-bot parity; Codex has no premium today)
    premium_values: set[str] | None = None
    premium_max_values: int | None = None

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
    template_data: Optional[Callable] = None     # () → (bytes, filename); returns template file content for download

    # dual_modal_input — second field
    modal_label_2: str = ""
    modal_placeholder_2: str = ""
    modal_min_length_2: int = 0
    modal_max_length_2: int = 500

    # dict_editor only
    dict_get_values: Optional[Callable] = None
    dict_set_value: Optional[Callable] = None
    dict_remove_value: Optional[Callable] = None
    dict_key_label: str = "Key"
    dict_value_label: str = "Value"
    dict_value_validator: Optional[Callable] = None
    dict_max_entries: Optional[int] = None

    # Discord permission requirements
    required_channel_perms: list[str] | None = None
    requires_role_manage: bool = False

    # Dashboard grouping per ADMIN_PANEL_STANDARD.md §7.
    category_group: str = "main"

    # Tier-aware label override (premium guilds render premium_label if set).
    premium_label: Optional[str] = None

    # Summary semantics:
    #   view_only       — read-only "View Status" entries; parent menu shows
    #                     "View only" instead of misleading "Not configured".
    #   default_summary — text shown on a menu when nothing under it is
    #                     customized (e.g. "Using defaults"). When set, the
    #                     menu reports "N of M customized" once values diverge.
    #   is_customized   — async (guild_id) -> bool. For leaf nodes that have a
    #                     baked-in default, returns True only when the user has
    #                     diverged from that default. When provided, parent
    #                     menus count customizations via this predicate rather
    #                     than the "values is non-empty" fallback.
    view_only: bool = False
    default_summary: Optional[str] = None
    is_customized: Optional[Callable] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

DASHBOARD_FEATURE_SEPARATOR_VALUE = "__feature_sep__"


def _effective_label(node: "PanelNode", is_premium: bool) -> str:
    """Return premium_label when the guild has premium and one is defined; else label."""
    if is_premium and node.premium_label:
        return node.premium_label
    return node.label


def _child_summary(kind: str, values: list, *, child: "PanelNode | None" = None) -> str:
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
        if child is not None and child.view_only:
            return "View only"
        if child is not None and child.children:
            total = len(child.children)
            if child.default_summary:
                return child.default_summary if n == 0 else f"{n} of {total} customized"
            if n == 0:
                return "Not configured"
            return f"{n} of {total} configured"
        # Stub (no children)
        if child is not None and child.default_summary:
            return "Customized" if n else child.default_summary
        return "Configured" if n else "Not configured"
    return f"{n} configured" if n else "Not set"


# ── Generic view builders ─────────────────────────────────────────────────────

def build_menu_view(
    node: PanelNode,
    summary_map: dict[str, list],
    on_select: Callable[[discord.Interaction, str], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
    is_premium: bool = False,
    back_label: str = "Done",
) -> discord.ui.LayoutView:
    """Build an overview menu view for a PanelNode with kind="menu".

    Args:
        node:        The menu PanelNode to render.
        summary_map: Pre-fetched {child_key: current_values_list} for all children.
        on_select:   Async callback (interaction, child_key) — navigate into child.
        on_cancel:   Async callback (interaction) — close / Done / Back.
        is_premium:  Whether the active guild has premium (drives _effective_label).
        back_label:  Label for the cancel button. "Done" closes; "Back" returns
                     to the parent (caller decides via `on_cancel`).
    """
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {_effective_label(node, is_premium)}")

    # Read-only description / context block (#4d0eb3 accent)
    desc_text = node.description
    if node.description_builder is not None:
        try:
            desc_text = node.description_builder(None)
        except Exception:
            pass
    if desc_text:
        builder.add_item(readonly_container(discord.ui.TextDisplay(desc_text)))

    # Editable block: per-child summaries + navigation select.
    child_lines = [
        f"- **{_effective_label(child, is_premium)}:** "
        f"{_child_summary(child.kind, summary_map.get(key, []), child=child)}"
        for key, child in node.children.items()
    ]

    if child_lines or node.children:
        if desc_text:
            builder.add_separator()

        editable_items: list[discord.ui.Item] = []
        if child_lines:
            editable_items.append(discord.ui.TextDisplay("\n".join(child_lines)))
        if node.children:
            editable_items.append(discord.ui.TextDisplay(
                "Select a category below to configure it."
            ))
            options = [
                discord.SelectOption(
                    label=_effective_label(child, is_premium),
                    value=key,
                    description=_child_summary(child.kind, summary_map.get(key, []), child=child),
                )
                for key, child in node.children.items()
            ]
            select = discord.ui.Select(
                placeholder="Select a category...",
                custom_id=cid("editor", "select", node.key),
                options=options,
            )

            async def _select_cb(interaction: discord.Interaction):
                await on_select(interaction, interaction.data["values"][0])

            select.callback = _select_cb
            select_row = discord.ui.ActionRow()
            select_row.add_item(select)
            editable_items.append(select_row)

        builder.add_item(editable_container(*editable_items))

    done_btn = discord.ui.Button(
        label=back_label,
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back" if back_label == "Back" else "done", node.key),
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
    is_premium: bool = False,
) -> discord.ui.LayoutView:
    """Build a select view for a PanelNode with kind in (role_select, channel_select, option_select).

    The component auto-saves on change (no explicit Save button); Back navigates
    to the parent; Clear (if provided) removes all values.
    """
    builder = AdminLayoutBuilder()

    node_label = _effective_label(node, is_premium)
    builder.add_header(f"## {node_label}")

    # Read-only description (#4d0eb3 accent)
    desc_text = node.description or f"Select values for **{node_label}**."
    builder.add_item(readonly_container(discord.ui.TextDisplay(desc_text)))

    # Build current-value text + select component
    if node.kind == "role_select":
        if current_values:
            mentions = [f"<@&{int(rid)}>" for rid in current_values]
            current_text = f"**Currently assigned:** {', '.join(mentions)}"
        else:
            current_text = "*No roles currently assigned.*"

    elif node.kind == "channel_select":
        if current_values:
            parts = [f"<#{int(cid_)}>" for cid_ in current_values]
            current_text = f"**Current channel:** {', '.join(parts)}"
        else:
            current_text = "*No channel currently set.*"

    elif node.kind == "option_select":
        if current_values:
            opt_label_map = {str(opt[0]): opt[1] for opt in (node.options or [])}
            names = [opt_label_map.get(str(v), str(v)) for v in current_values]
            current_text = f"**Currently selected:** {', '.join(names)}"
        else:
            current_text = "*Nothing currently selected.*"
    else:
        current_text = ""

    # Build the select component
    if node.kind == "role_select":
        component = discord.ui.RoleSelect(
            placeholder=f"Select roles for {node_label}...",
            custom_id=cid("editor", "select", node.key),
            min_values=node.min_values,
            max_values=node.max_values,
            default_values=[discord.Object(id=int(rid)) for rid in current_values],
        )

        async def _role_cb(interaction: discord.Interaction):
            role_ids = [int(rid) for rid in interaction.data.get("resolved", {}).get("roles", {}).keys()]
            await on_save(interaction, role_ids)

        component.callback = _role_cb

    elif node.kind == "channel_select":
        effective_max = node.max_values
        if is_premium and node.premium_max_values is not None:
            effective_max = node.premium_max_values
        select_kwargs = dict(
            placeholder=f"Select channel for {node_label}...",
            custom_id=cid("editor", "select", node.key),
            min_values=node.min_values,
            max_values=effective_max,
            default_values=[discord.Object(id=int(v)) for v in current_values],
        )
        if node.channel_types:
            select_kwargs["channel_types"] = node.channel_types
        component = discord.ui.ChannelSelect(**select_kwargs)

        async def _channel_cb(interaction: discord.Interaction):
            channel_ids = [int(cid_) for cid_ in interaction.data.get("values", [])]
            await on_save(interaction, channel_ids)

        component.callback = _channel_cb

    elif node.kind == "option_select":
        current_strs = [str(v) for v in current_values]
        _prem = node.premium_values or set()
        option_objects = []
        for opt in (node.options or []):
            val, lbl = str(opt[0]), opt[1]
            desc = opt[2] if len(opt) > 2 else None
            if val in _prem and not is_premium:
                lbl = f"💎 {lbl}"
                desc = "Requires Premium subscription"
            option_objects.append(
                discord.SelectOption(
                    label=lbl,
                    value=val,
                    description=desc,
                    default=(val in current_strs),
                )
            )
        component = discord.ui.Select(
            placeholder="Select one or more options...",
            custom_id=cid("editor", "select", node.key),
            min_values=node.min_values,
            max_values=min(node.max_values, len(option_objects)) if option_objects else 1,
            options=option_objects,
        )

        async def _option_cb(interaction: discord.Interaction):
            await on_save(interaction, interaction.data["values"])

        component.callback = _option_cb

    else:
        return create_empty_layout(f"Unknown node kind: {node.kind!r}")

    # Wrap current-value text + active select in editable_container (no accent)
    select_row = discord.ui.ActionRow()
    select_row.add_item(component)
    builder.add_item(editable_container(
        discord.ui.TextDisplay(current_text or f"**Edit {node_label}:**"),
        select_row,
    ))

    # Back + optional Clear row at root
    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=cid("editor", "back", node.key),
    )
    back_btn.callback = on_back
    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "clear", node.key),
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
    attempted: Optional[str] = None,
    is_premium: bool = False,
) -> discord.ui.LayoutView:
    """Build a trigger view for a PanelNode with kind="modal_input".

    Shows the current value and a button that opens a modal for editing.
    on_save receives (button_interaction, modal_interaction, raw_value).
    When `attempted` is supplied (after a validation failure), the modal opens
    pre-filled with that value instead of the current one.
    """
    builder = AdminLayoutBuilder()

    node_label = _effective_label(node, is_premium)
    builder.add_header(f"## {node_label}")

    desc_text = node.description or f"Set a value for **{node_label}**."
    builder.add_item(readonly_container(discord.ui.TextDisplay(desc_text)))

    current_text = (
        f"**Current value:** {current_values[0]}" if current_values
        else "*Not currently set.*"
    )

    set_btn = discord.ui.Button(
        label=f"Set {node_label}",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "set", node.key),
    )

    async def set_btn_callback(bi: discord.Interaction):
        async def _on_submit(mi: discord.Interaction, raw: str):
            await on_save(bi, mi, raw)

        if attempted is not None:
            modal_default = attempted
        elif current_values:
            modal_default = current_values[0]
        else:
            modal_default = ""

        modal = PanelInputModal(
            title=node.modal_title or f"Set {node_label}",
            label=node.modal_label or "Value",
            placeholder=node.modal_placeholder or "",
            min_length=node.modal_min_length,
            max_length=node.modal_max_length,
            default=modal_default,
            on_submit_callback=_on_submit,
            paragraph=node.modal_paragraph,
            required=node.modal_required,
        )
        await bi.response.send_modal(modal)

    set_btn.callback = set_btn_callback

    set_row = discord.ui.ActionRow()
    set_row.add_item(set_btn)
    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "clear", node.key),
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        set_row.add_item(clear_btn)

    builder.add_item(editable_container(
        discord.ui.TextDisplay(current_text),
        set_row,
    ))

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=cid("editor", "back", node.key),
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
    is_premium: bool = False,
) -> discord.ui.LayoutView:
    """Build a trigger view for a PanelNode with kind="dual_modal_input"."""
    builder = AdminLayoutBuilder()

    node_label = _effective_label(node, is_premium)
    builder.add_header(f"## {node_label}")

    val1 = current_values[0] if len(current_values) > 0 else ""
    val2 = current_values[1] if len(current_values) > 1 else ""

    desc_text = node.description or f"Set values for **{node_label}**."
    builder.add_item(readonly_container(discord.ui.TextDisplay(desc_text)))

    if val1 or val2:
        lines = []
        if val1:
            lines.append(f"**{node.modal_label or 'Field 1'}:** {val1}")
        if val2:
            lines.append(f"**{node.modal_label_2 or 'Field 2'}:** {val2}")
        current_text = "\n".join(lines)
    else:
        current_text = "*Not currently set.*"

    edit_btn = discord.ui.Button(
        label="Edit",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "edit", node.key),
    )

    async def edit_btn_callback(bi: discord.Interaction):
        async def _on_submit(mi: discord.Interaction, raw1: str, raw2: str):
            await on_save(bi, mi, raw1, raw2)

        modal = _PanelDualInputModal(
            title=node.modal_title or f"Set {node_label}",
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

    edit_row = discord.ui.ActionRow()
    edit_row.add_item(edit_btn)
    builder.add_item(editable_container(
        discord.ui.TextDisplay(current_text),
        edit_row,
    ))

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=cid("editor", "back", node.key),
    )
    back_btn.callback = on_back
    back_row = discord.ui.ActionRow()
    back_row.add_item(back_btn)
    builder.add_item(back_row)

    return builder.build()


# ── File upload modal + status view ──────────────────────────────────────────

class PanelFileUploadModal(discord.ui.Modal):
    """Modal with a single file upload field for panel file_upload nodes."""

    def __init__(self, *, title: str, node_key: str, on_submit_callback: Callable):
        super().__init__(title=title)
        self._callback = on_submit_callback
        self.upload_label = discord.ui.Label(
            text="JSON File",
            component=discord.ui.FileUpload(
                custom_id=cid("modal", "upload", node_key),
                min_values=1,
                max_values=1,
            ),
        )
        self.add_item(self.upload_label)

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
    is_premium: bool = False,
) -> discord.ui.LayoutView:
    """Build a status view for a PanelNode with kind="file_upload"."""
    builder = AdminLayoutBuilder()

    node_label = _effective_label(node, is_premium)
    builder.add_header(f"## {node_label}")

    if node.description:
        builder.add_item(readonly_container(discord.ui.TextDisplay(node.description)))

    if current_values:
        current_text = "**Custom JSON:** ✅ Active"
    else:
        current_text = "**Custom JSON:** ⬜ Not set — using default layout"

    btn_row = discord.ui.ActionRow()

    if on_upload is not None:
        upload_btn = discord.ui.Button(
            label="Upload JSON",
            style=discord.ButtonStyle.primary,
            custom_id=cid("editor", "upload", node.key),
        )

        async def upload_btn_cb(bi: discord.Interaction):
            async def _on_submit(mi, attachment):
                await on_upload(bi, mi, attachment)

            modal = PanelFileUploadModal(
                title=f"Upload {node_label}",
                node_key=node.key,
                on_submit_callback=_on_submit,
            )
            await bi.response.send_modal(modal)

        upload_btn.callback = upload_btn_cb
        btn_row.add_item(upload_btn)

    if node.template_data is not None:
        import io
        template_btn = discord.ui.Button(
            label="Download Template",
            style=discord.ButtonStyle.secondary,
            custom_id=cid("editor", "template", node.key),
        )

        async def template_btn_cb(ti: discord.Interaction):
            template_bytes, filename = node.template_data()
            await ti.response.send_message(
                file=discord.File(io.BytesIO(template_bytes), filename=filename),
                ephemeral=True,
            )

        template_btn.callback = template_btn_cb
        btn_row.add_item(template_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "clear", node.key),
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        btn_row.add_item(clear_btn)

    # Editable block: current payload + upload/template/clear buttons.
    builder.add_item(editable_container(
        discord.ui.TextDisplay(current_text),
        btn_row,
    ))

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=cid("editor", "back", node.key),
    )
    back_btn.callback = on_back
    back_row = discord.ui.ActionRow()
    back_row.add_item(back_btn)
    builder.add_item(back_row)

    return builder.build()


# ── Overview (Dashboard / Message 1) ─────────────────────────────────────────

_UNCONFIGURED_STRINGS = {"Not configured", "Not set", "Not assigned", "Default", "View only"}


def _compact_category_summary(
    cat_node: PanelNode,
    cat_summaries: dict[str, str | dict[str, str]],
    toggle: bool | None,
) -> str:
    """One-line compact summary of how many child values are configured."""
    configured = 0
    total = 0
    for child_key, child_node in cat_node.children.items():
        if getattr(child_node, "view_only", False):
            continue
        val = cat_summaries.get(child_key, "Not configured")
        if isinstance(val, dict):
            for sub_key, sub_val in val.items():
                sub_node = child_node.children.get(sub_key) if child_node.children else None
                if sub_node is not None and getattr(sub_node, "view_only", False):
                    continue
                total += 1
                if sub_val not in _UNCONFIGURED_STRINGS:
                    configured += 1
        else:
            total += 1
            if val not in _UNCONFIGURED_STRINGS:
                configured += 1
    if total == 0:
        return ""
    if configured == 0:
        return "Not configured"
    return f"{configured} of {total} configured"


def build_overview_view(
    root_node: PanelNode,
    deep_summary: dict[str, dict[str, str | dict[str, str]]],
    toggle_states: dict[str, bool | None],
    locked_keys: set[str],
    on_category_select: Callable[[discord.Interaction, str], Awaitable[None]],
    preamble_items: list[discord.ui.Item] | None = None,
    extra_buttons: list[discord.ui.Button] | None = None,
    compact: bool = True,
    title_override: str | None = None,
    footer_text: str | None = None,
    is_premium: bool = False,
) -> discord.ui.LayoutView:
    """Build the persistent overview view (Message 1) per ADMIN_PANEL_STANDARD.md §1."""
    from .base import build_notice_layout

    builder = AdminLayoutBuilder()
    _locked = locked_keys or set()

    header_text = title_override if title_override is not None else root_node.label
    builder.add_header(f"## {header_text}")

    if preamble_items:
        builder.add_item(readonly_container(*preamble_items))

    detail_items: list[discord.ui.Item] = []
    if compact:
        lines = []
        for cat_key, cat_node in root_node.children.items():
            cat_summaries = deep_summary.get(cat_key, {})
            lock_prefix = "\U0001f512 " if cat_key in _locked else ""
            toggle = toggle_states.get(cat_key)
            summary = _compact_category_summary(cat_node, cat_summaries, toggle)
            cat_label = _effective_label(cat_node, is_premium)
            if toggle is not None:
                status = "Enabled" if toggle else "Disabled"
                lines.append(f"**{lock_prefix}{cat_label}** - {status} ({summary})")
            else:
                lines.append(f"**{lock_prefix}{cat_label}** - {summary}")
        detail_items.append(discord.ui.TextDisplay("\n".join(lines)))
    else:
        for cat_key, cat_node in root_node.children.items():
            cat_summaries = deep_summary.get(cat_key, {})
            lock_prefix = "\U0001f512 " if cat_key in _locked else ""
            toggle = toggle_states.get(cat_key)
            cat_label = _effective_label(cat_node, is_premium)
            if toggle is not None:
                status = "Enabled" if toggle else "Disabled"
                header = f"**{lock_prefix}{cat_label}** - {status}"
            else:
                header = f"**{lock_prefix}{cat_label}**"
            cat_lines = [header]
            for child_key, child_node in cat_node.children.items():
                val = cat_summaries.get(child_key, "Not configured")
                child_label = _effective_label(child_node, is_premium)
                if isinstance(val, dict):
                    cat_lines.append(f"  {child_label}:")
                    for sub_key, sub_node in child_node.children.items():
                        sub_val = val.get(sub_key, "Not configured")
                        sub_label = _effective_label(sub_node, is_premium)
                        cat_lines.append(f"    • {sub_label}: {sub_val}")
                else:
                    cat_lines.append(f"  • {child_label}: {val}")
            detail_items.append(discord.ui.TextDisplay("\n".join(cat_lines)))

    if detail_items:
        builder.add_item(readonly_container(*detail_items))

    builder.add_text("Select a category below to configure it.")

    options: list[discord.SelectOption] = []
    prev_group: str | None = None
    for key, child in root_node.children.items():
        group = getattr(child, "category_group", "main")
        if group == "feature" and prev_group == "main":
            options.append(discord.SelectOption(
                label="── Feature Configurations ──",
                value=DASHBOARD_FEATURE_SEPARATOR_VALUE,
                description="(divider — not selectable)",
            ))
        child_label = _effective_label(child, is_premium)
        options.append(discord.SelectOption(
            label=f"\U0001f512 {child_label}" if key in _locked else child_label,
            value=key,
            description=child.description[:100] if child.description else None,
        ))
        prev_group = group
    select = discord.ui.Select(
        placeholder="Select a category...",
        custom_id=cid("dash", "select"),
        options=options,
    )

    async def _select_cb(interaction: discord.Interaction):
        chosen = interaction.data["values"][0]
        if chosen == DASHBOARD_FEATURE_SEPARATOR_VALUE:
            await interaction.response.send_message(
                view=build_notice_layout(
                    "Pick a category",
                    "That line is a divider — choose an actual category.",
                ),
                ephemeral=True,
            )
            return
        await on_category_select(interaction, chosen)

    select.callback = _select_cb
    builder.add_select(select)

    if extra_buttons:
        row = discord.ui.ActionRow()
        for btn in extra_buttons:
            row.add_item(btn)
        builder.add_item(row)

    if footer_text:
        builder.add_separator()
        builder.add_text(footer_text)

    return builder.build()


# ── Dict Editor (scaffolded for cross-bot parity) ────────────────────────────

def build_dict_editor_view(
    node: PanelNode,
    current_values: dict,
    *,
    on_add: Callable[[discord.Interaction], Awaitable[None]],
    on_edit: Callable[[discord.Interaction, str], Awaitable[None]],
    on_remove: Callable[[discord.Interaction, str], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    back_label: str = "Back",
    is_premium: bool = False,
) -> discord.ui.LayoutView:
    """Build a view for a PanelNode with kind="dict_editor"."""
    builder = AdminLayoutBuilder()

    builder.add_header(f"## {_effective_label(node, is_premium)}")

    if node.description:
        builder.add_item(readonly_container(discord.ui.TextDisplay(node.description)))

    if current_values:
        lines = [f"• **{k}**: {v}" for k, v in current_values.items()]
        if node.dict_max_entries is not None:
            lines.append(f"\n*{len(current_values)} of {node.dict_max_entries} entries*")
        current_text = "\n".join(lines)
    else:
        current_text = "*No entries configured.*"

    add_disabled = (
        node.dict_max_entries is not None
        and len(current_values) >= node.dict_max_entries
    )
    add_btn = discord.ui.Button(
        label="Add Entry",
        style=discord.ButtonStyle.success,
        custom_id=cid("editor", "dict_add", node.key),
        disabled=add_disabled,
    )
    add_btn.callback = on_add

    editor_items: list[discord.ui.Item] = [discord.ui.TextDisplay(current_text)]
    add_row = discord.ui.ActionRow()
    add_row.add_item(add_btn)
    editor_items.append(add_row)

    if current_values:
        entry_options = [
            discord.SelectOption(label=str(k)[:100], value=str(k))
            for k in list(current_values.keys())[:25]
        ]
        edit_select = discord.ui.Select(
            placeholder="Edit entry...",
            custom_id=cid("editor", "dict_edit", node.key),
            options=entry_options,
            min_values=1,
            max_values=1,
        )

        async def _edit_cb(interaction: discord.Interaction):
            await on_edit(interaction, interaction.data["values"][0])

        edit_select.callback = _edit_cb

        remove_select = discord.ui.Select(
            placeholder="Remove entry...",
            custom_id=cid("editor", "dict_remove", node.key),
            options=entry_options,
            min_values=1,
            max_values=1,
        )

        async def _remove_cb(interaction: discord.Interaction):
            await on_remove(interaction, interaction.data["values"][0])

        remove_select.callback = _remove_cb

        edit_row = discord.ui.ActionRow()
        edit_row.add_item(edit_select)
        editor_items.append(edit_row)

        remove_row = discord.ui.ActionRow()
        remove_row.add_item(remove_select)
        editor_items.append(remove_row)

    builder.add_item(editable_container(*editor_items))

    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=cid("editor", "dict_back", node.key),
    )
    back_btn.callback = on_back
    builder.add_action_row(back_btn)

    return builder.build()
