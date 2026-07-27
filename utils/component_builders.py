"""
Shared Components V2 Builders

Reusable rendering functions for Discord Components V2 layouts.
Used by the greeting, guide, and info board renderers.

Button building is feature-specific (different custom_id encoding),
so button_builder is passed as a callback.
"""

from typing import Any, Callable, Dict, Optional

import discord
from discord.components import MediaGalleryItem

_STYLE_MAP = {
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
    "danger":    discord.ButtonStyle.danger,
    "link":      discord.ButtonStyle.link,
}

# Callback type for feature-specific button building.
# Signature: (btn_def, placeholders) -> discord.ui.Button
ButtonBuilder = Callable[[Dict[str, Any], Dict[str, str]], discord.ui.Button]

# Callback type for feature-specific select building.
# Signature: (sel_def, placeholders) -> discord.ui.Select
SelectBuilder = Callable[[Dict[str, Any], Dict[str, str]], discord.ui.Select]


def resolve_color(raw: Any) -> int:
    """Convert a hex string or int to an integer color value."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.startswith("#"):
        return int(raw.lstrip("#"), 16)
    return 0x5865F2


def apply_placeholders(text: str, placeholders: Dict[str, str]) -> str:
    """Replace placeholder tokens in text."""
    for k, v in placeholders.items():
        text = text.replace(k, v)
    return text


def build_text(comp: Dict[str, Any], placeholders: Dict[str, str]) -> discord.ui.TextDisplay:
    content = apply_placeholders(comp.get("content", ""), placeholders)
    return discord.ui.TextDisplay(content)


def build_separator() -> discord.ui.Separator:
    return discord.ui.Separator()


def build_thumbnail(
    acc_def: Dict[str, Any],
    resolve_media: Optional[Callable[[str], str]] = None,
) -> discord.ui.Thumbnail:
    """Build a thumbnail component.

    resolve_media: optional callback to resolve special media values like "member_avatar".
    """
    media = acc_def.get("media", "")
    if resolve_media:
        media = resolve_media(media)
    description = acc_def.get("description")
    return discord.ui.Thumbnail(media=media, description=description)


def build_section(
    comp: Dict[str, Any],
    placeholders: Dict[str, str],
    button_builder: ButtonBuilder,
    resolve_media: Optional[Callable[[str], str]] = None,
) -> discord.ui.Section:
    acc_def = comp.get("accessory", {})
    acc_type = acc_def.get("type")
    if acc_type == "thumbnail":
        accessory = build_thumbnail(acc_def, resolve_media)
    else:
        accessory = button_builder(acc_def, placeholders)

    section = discord.ui.Section(accessory=accessory)
    for text_comp in comp.get("content", []):
        section.add_item(build_text(text_comp, placeholders))
    return section


def build_action_row(
    comp: Dict[str, Any],
    placeholders: Dict[str, str],
    button_builder: ButtonBuilder,
    select_builder: Optional[SelectBuilder] = None,
) -> discord.ui.ActionRow:
    row = discord.ui.ActionRow()
    if "select" in comp and select_builder:
        row.add_item(select_builder(comp["select"], placeholders))
    else:
        for btn_def in comp.get("buttons", []):
            row.add_item(button_builder(btn_def, placeholders))
    return row


def build_media_gallery(comp: Dict[str, Any]) -> discord.ui.MediaGallery:
    items = [
        MediaGalleryItem(
            media=item["media"],
            description=item.get("description"),
            spoiler=item.get("spoiler", False),
        )
        for item in comp["items"]
    ]
    return discord.ui.MediaGallery(*items)


def build_container(
    comp: Dict[str, Any],
    placeholders: Dict[str, str],
    button_builder: ButtonBuilder,
    select_builder: Optional[SelectBuilder] = None,
    resolve_media: Optional[Callable[[str], str]] = None,
) -> discord.ui.Container:
    children = []
    for child in comp.get("components", []):
        item = build_component(child, placeholders, button_builder, select_builder, resolve_media)
        if item is not None:
            children.append(item)
    container = discord.ui.Container(*children, spoiler=comp.get("spoiler", False))
    if comp.get("accent_color"):
        container.accent_colour = resolve_color(comp["accent_color"])
    return container


def build_component(
    comp: Dict[str, Any],
    placeholders: Dict[str, str],
    button_builder: ButtonBuilder,
    select_builder: Optional[SelectBuilder] = None,
    resolve_media: Optional[Callable[[str], str]] = None,
):
    """Build a single component from its JSON definition. Returns None for unknown types."""
    comp_type = comp.get("type")
    if comp_type == "separator":
        return build_separator()
    if comp_type == "text":
        return build_text(comp, placeholders)
    if comp_type == "section":
        return build_section(comp, placeholders, button_builder, resolve_media)
    if comp_type == "action_row":
        return build_action_row(comp, placeholders, button_builder, select_builder)
    if comp_type == "container":
        return build_container(comp, placeholders, button_builder, select_builder, resolve_media)
    if comp_type == "media_gallery":
        return build_media_gallery(comp)
    return None


def build_link_button(btn_def: Dict[str, Any], placeholders: Dict[str, str]) -> discord.ui.Button:
    """Build a link-style button (shared across features)."""
    label = apply_placeholders(btn_def.get("label", "Button"), placeholders)
    return discord.ui.Button(
        style=discord.ButtonStyle.link,
        label=label,
        url=btn_def.get("url"),
        emoji=btn_def.get("emoji"),
        disabled=btn_def.get("disabled", False),
    )
