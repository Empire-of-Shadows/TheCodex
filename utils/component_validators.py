"""
Shared Components V2 Validators

Reusable validation functions for Discord Components V2 JSON schemas.
Used by both the welcome-builder and guide-builder systems.

All validators return (bool, str) - True/"" on success, or False/error message.
Button/select action validation is delegated to a feature-specific callback.

Error messages use human-readable paths:
  - Arrow (→) separates path segments: "Container #1 → Text #2"
  - Dash (-) separates path from error: "Button #1 - label must be a non-empty string."
"""

import re
from typing import Any, Callable, Optional, Tuple

_VALID_BUTTON_STYLES = {"primary", "secondary", "success", "danger", "link"}
_VALID_TOP_LEVEL_TYPES = {"separator", "text", "section", "action_row", "container", "media_gallery"}
_VALID_ACCENT_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Type alias for the feature-specific action validator callback.
# Signature: (comp_dict, prefix) -> (bool, error_message)
ActionValidator = Callable[[dict, str], Tuple[bool, str]]

_TYPE_LABELS = {
    "text": "Text",
    "section": "Section",
    "action_row": "Action Row",
    "container": "Container",
    "media_gallery": "Gallery",
    "separator": "Separator",
}


def trunc_label(label: str, max_len: int = 30) -> str:
    """Truncate a label for display in error messages."""
    if len(label) <= max_len:
        return label
    return label[:max_len - 3] + "..."


def _component_label(comp: Any, idx: int) -> str:
    """Build a human-readable label for a component by type and position."""
    if not isinstance(comp, dict):
        return f"Component #{idx + 1}"
    comp_type = comp.get("type", "")
    type_name = _TYPE_LABELS.get(comp_type, comp_type.title() if comp_type else "Component")
    return f"{type_name} #{idx + 1}"


def _button_label(btn: Any, idx: int) -> str:
    """Build a human-readable label for a button."""
    if isinstance(btn, dict):
        label = btn.get("label")
        if isinstance(label, str) and label:
            return f'Button "{trunc_label(label)}"'
    return f"Button #{idx + 1}"


def _option_label(opt: Any, idx: int) -> str:
    """Build a human-readable label for a select option."""
    if isinstance(opt, dict):
        label = opt.get("label")
        if isinstance(label, str) and label:
            return f'Option "{trunc_label(label)}"'
    return f"Option #{idx + 1}"


def validate_accent_color(value: Any) -> Tuple[bool, str]:
    if isinstance(value, int):
        if 0 <= value <= 16777215:
            return True, ""
        return False, f"accent_color integer {value} is out of range (0\u201316777215)."
    if isinstance(value, str):
        if _VALID_ACCENT_COLOR_RE.match(value):
            return True, ""
        return False, f"accent_color string \"{value}\" must be in #RRGGBB format."
    return False, "accent_color must be a hex string (#RRGGBB) or an integer."


def validate_text(comp: dict, prefix: str) -> Tuple[bool, str]:
    content = comp.get("content")
    if not isinstance(content, str) or not content:
        return False, f"{prefix} \u2014 content must be a non-empty string."
    if len(content) > 4000:
        return False, f"{prefix} \u2014 content exceeds 4000 characters."
    return True, ""


def validate_thumbnail(comp: dict, prefix: str) -> Tuple[bool, str]:
    media = comp.get("media")
    if not isinstance(media, str) or not media:
        return False, f"{prefix} \u2014 media must be a non-empty string."
    if media != "member_avatar":
        return False, (
            f"{prefix} \u2014 media must be \"member_avatar\". "
            f"Thumbnails do not support external URLs \u2014 use a single-item media_gallery instead."
        )
    return True, ""


def validate_section(
    comp: dict,
    prefix: str,
    action_validator: Optional[ActionValidator] = None,
) -> Tuple[bool, str]:
    # content: 1-3 text objects
    content = comp.get("content")
    if not isinstance(content, list) or len(content) == 0:
        return False, f"{prefix} \u2014 content must be a non-empty array."
    if len(content) > 3:
        return False, f"{prefix} \u2014 content has {len(content)} items; max is 3."
    for i, item in enumerate(content):
        item_prefix = f"{prefix} \u2192 Text #{i + 1}"
        if not isinstance(item, dict) or item.get("type") != "text":
            return False, f"{item_prefix} \u2014 must be a text component ({{\"type\": \"text\", ...}})."
        ok, msg = validate_text(item, item_prefix)
        if not ok:
            return False, msg

    # accessory: required, thumbnail or button
    accessory = comp.get("accessory")
    if accessory is None:
        return False, f"{prefix} \u2014 accessory is required."
    if not isinstance(accessory, dict):
        return False, f"{prefix} \u2192 Accessory \u2014 must be an object."
    acc_prefix = f"{prefix} \u2192 Accessory"
    acc_type = accessory.get("type")
    if acc_type == "thumbnail":
        return validate_thumbnail(accessory, acc_prefix)
    if acc_type == "button":
        if action_validator:
            return action_validator(accessory, acc_prefix)
        return _validate_button_structure(accessory, acc_prefix)
    return False, f"{acc_prefix} \u2014 type \"{acc_type}\" is invalid; must be \"thumbnail\" or \"button\"."


def validate_action_row(
    comp: dict,
    prefix: str,
    action_validator: Optional[ActionValidator] = None,
    select_validator: Optional[ActionValidator] = None,
) -> Tuple[bool, str]:
    has_buttons = "buttons" in comp
    has_select = "select" in comp

    if has_buttons and has_select:
        return False, f"{prefix} \u2014 cannot have both \"buttons\" and \"select\"; they are mutually exclusive."
    if not has_buttons and not has_select:
        return False, f"{prefix} \u2014 must have either \"buttons\" or \"select\"."

    if has_select:
        select_prefix = f"{prefix} \u2192 Select menu"
        if select_validator:
            return select_validator(comp["select"], select_prefix)
        return validate_string_select(comp["select"], select_prefix)

    buttons = comp["buttons"]
    if not isinstance(buttons, list) or len(buttons) == 0:
        return False, f"{prefix} \u2014 buttons must be a non-empty array."
    if len(buttons) > 5:
        return False, f"{prefix} \u2014 buttons has {len(buttons)} items; max is 5."
    for i, btn in enumerate(buttons):
        btn_prefix = f"{prefix} \u2192 {_button_label(btn, i)}"
        if action_validator:
            ok, msg = action_validator(btn, btn_prefix)
        else:
            ok, msg = _validate_button_structure(btn, btn_prefix)
        if not ok:
            return False, msg
    return True, ""


def validate_string_select(comp: Any, prefix: str, option_validator: Optional[ActionValidator] = None) -> Tuple[bool, str]:
    if not isinstance(comp, dict):
        return False, f"{prefix} \u2014 must be an object."

    placeholder = comp.get("placeholder")
    if placeholder is not None:
        if not isinstance(placeholder, str):
            return False, f"{prefix} \u2014 placeholder must be a string."
        if len(placeholder) > 150:
            return False, f"{prefix} \u2014 placeholder exceeds 150 characters."

    options = comp.get("options")
    if not isinstance(options, list) or len(options) == 0:
        return False, f"{prefix} \u2014 options must be a non-empty array."
    if len(options) > 25:
        return False, f"{prefix} \u2014 options has {len(options)} items; max is 25."

    for i, opt in enumerate(options):
        opt_prefix = f"{prefix} \u2192 {_option_label(opt, i)}"
        if option_validator:
            ok, msg = option_validator(opt, opt_prefix)
        else:
            ok, msg = _validate_select_option_structure(opt, opt_prefix)
        if not ok:
            return False, msg

    for field_name in ("min_values", "max_values"):
        val = comp.get(field_name)
        if val is not None:
            if not isinstance(val, int) or not (1 <= val <= 25):
                return False, f"{prefix} \u2014 {field_name} must be an integer between 1 and 25."

    return True, ""


def validate_container(
    comp: dict,
    prefix: str,
    action_validator: Optional[ActionValidator] = None,
    select_validator: Optional[ActionValidator] = None,
) -> Tuple[bool, str]:
    if "accent_color" in comp:
        ok, msg = validate_accent_color(comp["accent_color"])
        if not ok:
            return False, f"{prefix} \u2014 {msg}"

    if "spoiler" in comp and not isinstance(comp["spoiler"], bool):
        return False, f"{prefix} \u2014 spoiler must be a boolean."

    components = comp.get("components")
    if not isinstance(components, list) or len(components) == 0:
        return False, f"{prefix} \u2014 components must be a non-empty array."
    if len(components) > 10:
        return False, f"{prefix} \u2014 components has {len(components)} items; max is 10."

    allowed_child_types = {"separator", "text", "section", "action_row", "media_gallery"}
    for i, child in enumerate(components):
        child_prefix = f"{prefix} \u2192 {_component_label(child, i)}"
        if not isinstance(child, dict):
            return False, f"{child_prefix} \u2014 must be an object."
        child_type = child.get("type")
        if child_type not in allowed_child_types:
            return False, (
                f"{child_prefix} \u2014 type \"{child_type}\" is invalid inside a container. "
                f"Allowed: {', '.join(sorted(allowed_child_types))}."
            )
        if child_type == "separator":
            continue
        ok, msg = _validate_child_component(
            child, child_type, child_prefix,
            action_validator=action_validator,
            select_validator=select_validator,
        )
        if not ok:
            return False, msg

    return True, ""


def validate_media_gallery(comp: dict, prefix: str) -> Tuple[bool, str]:
    items = comp.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return False, f"{prefix} \u2014 items must be a non-empty array."
    if len(items) > 10:
        return False, f"{prefix} \u2014 items has {len(items)} items; max is 10."

    for i, item in enumerate(items):
        item_prefix = f"{prefix} \u2192 Image #{i + 1}"
        if not isinstance(item, dict):
            return False, f"{item_prefix} \u2014 must be an object."
        media = item.get("media")
        if not isinstance(media, str) or not media.startswith("https://"):
            return False, f"{item_prefix} \u2014 media must be an https:// URL."
        description = item.get("description")
        if description is not None:
            if not isinstance(description, str):
                return False, f"{item_prefix} \u2014 description must be a string."
            if len(description) > 256:
                return False, f"{item_prefix} \u2014 description exceeds 256 characters."
        if "spoiler" in item and not isinstance(item["spoiler"], bool):
            return False, f"{item_prefix} \u2014 spoiler must be a boolean."

    return True, ""


def validate_top_level_component(
    comp: Any,
    idx: int,
    action_validator: Optional[ActionValidator] = None,
    select_validator: Optional[ActionValidator] = None,
) -> Tuple[bool, str]:
    """Validate a single top-level component (text, separator, section, etc.)."""
    prefix = _component_label(comp, idx)
    if not isinstance(comp, dict):
        return False, f"{prefix} \u2014 must be an object."
    comp_type = comp.get("type")
    if comp_type not in _VALID_TOP_LEVEL_TYPES:
        return False, (
            f"{prefix} \u2014 type \"{comp_type}\" is invalid. "
            f"Top-level types: {', '.join(sorted(_VALID_TOP_LEVEL_TYPES))}."
        )
    if comp_type == "separator":
        return True, ""
    return _validate_child_component(
        comp, comp_type, prefix,
        action_validator=action_validator,
        select_validator=select_validator,
    )


def validate_components_list(
    components: Any,
    action_validator: Optional[ActionValidator] = None,
    select_validator: Optional[ActionValidator] = None,
    max_items: int = 10,
) -> Tuple[bool, str]:
    """Validate a components array (used at top level or inside containers)."""
    if not isinstance(components, list) or len(components) == 0:
        return False, "components must be a non-empty array."
    if len(components) > max_items:
        return False, f"components has {len(components)} items; max is {max_items}."

    for i, comp in enumerate(components):
        ok, msg = validate_top_level_component(comp, i, action_validator, select_validator)
        if not ok:
            return False, msg

    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers (structural validation without action semantics)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_button_structure(comp: dict, prefix: str) -> Tuple[bool, str]:
    """Validate button structure only (no action semantics)."""
    if not isinstance(comp, dict):
        return False, f"{prefix} \u2014 must be an object."
    style = comp.get("style")
    if style not in _VALID_BUTTON_STYLES:
        return False, (
            f"{prefix} \u2014 style \"{style}\" is invalid. "
            f"Valid styles: {', '.join(sorted(_VALID_BUTTON_STYLES))}."
        )
    label = comp.get("label")
    if not isinstance(label, str) or not label:
        return False, f"{prefix} \u2014 label must be a non-empty string."
    if len(label) > 80:
        return False, f"{prefix} \u2014 label exceeds 80 characters."
    if style == "link":
        url = comp.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            return False, f"{prefix} \u2014 url is required for link buttons and must start with https://."
    return True, ""


def _validate_select_option_structure(opt: Any, prefix: str) -> Tuple[bool, str]:
    """Validate select option structure only (no action semantics)."""
    if not isinstance(opt, dict):
        return False, f"{prefix} \u2014 must be an object."
    label = opt.get("label")
    if not isinstance(label, str) or not label:
        return False, f"{prefix} \u2014 label must be a non-empty string."
    if len(label) > 100:
        return False, f"{prefix} \u2014 label exceeds 100 characters."
    description = opt.get("description")
    if description is not None:
        if not isinstance(description, str):
            return False, f"{prefix} \u2014 description must be a string."
        if len(description) > 100:
            return False, f"{prefix} \u2014 description exceeds 100 characters."
    emoji = opt.get("emoji")
    if emoji is not None and not isinstance(emoji, str):
        return False, f"{prefix} \u2014 emoji must be a string."
    return True, ""


def _validate_child_component(
    comp: dict,
    comp_type: str,
    prefix: str,
    action_validator: Optional[ActionValidator] = None,
    select_validator: Optional[ActionValidator] = None,
) -> Tuple[bool, str]:
    """Dispatch validation for a component by type."""
    if comp_type == "text":
        return validate_text(comp, prefix)
    if comp_type == "section":
        return validate_section(comp, prefix, action_validator)
    if comp_type == "action_row":
        return validate_action_row(comp, prefix, action_validator, select_validator)
    if comp_type == "container":
        return validate_container(comp, prefix, action_validator, select_validator)
    if comp_type == "media_gallery":
        return validate_media_gallery(comp, prefix)
    return True, ""
