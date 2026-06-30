"""
Welcome Message Schema Validator

Validates the JSON config for the JSON-driven welcome message builder.
All validation is synchronous and returns (bool, str) — success or first error.

Delegates structural component validation to the shared component_validators module.
Button/select action validation is welcome-specific (validates against VALID_ACTIONS).
"""

import json
from typing import Any, Tuple

from Features.NewMembers.welcome_actions import VALID_ACTIONS, encode_custom_id
from utils.component_validators import (
    validate_accent_color,
    validate_components_list,
)

_VALID_BUTTON_STYLES = {"primary", "secondary", "success", "danger", "link"}

# Hard ceiling on the serialized payload. The per-field length/count limits
# already bound a *well-formed* layout; this stops a caller from smuggling
# megabytes of junk in unrecognised keys (which would otherwise be stored
# verbatim) and bloating the guild config document.
_MAX_WELCOME_BYTES = 64 * 1024
_ALLOWED_TOP_LEVEL = {"accent_color", "components"}


def validate_welcome_schema(data: Any) -> Tuple[bool, str]:
    """Validate a welcome components JSON config dict.

    Returns (True, "") on success or (False, human-readable error) on first failure.
    """
    if not isinstance(data, dict):
        return False, "Top-level value must be a JSON object."

    try:
        size = len(json.dumps(data, default=str))
    except (TypeError, ValueError):
        return False, "Payload is not JSON-serializable."
    if size > _MAX_WELCOME_BYTES:
        return False, f"Welcome payload is too large ({size} bytes; max {_MAX_WELCOME_BYTES})."

    unknown = set(data) - _ALLOWED_TOP_LEVEL
    if unknown:
        return False, f"Unknown top-level field(s): {', '.join(sorted(unknown))}."

    # Optional accent_color
    if "accent_color" in data:
        ok, msg = validate_accent_color(data["accent_color"])
        if not ok:
            return False, msg

    # Required components
    if "components" not in data:
        return False, "Missing required field: \"components\"."

    return validate_components_list(
        data["components"],
        action_validator=_validate_welcome_button,
        select_validator=_validate_welcome_select,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Welcome-specific action validators
# ─────────────────────────────────────────────────────────────────────────────

def _validate_welcome_button(comp: dict, prefix: str) -> Tuple[bool, str]:
    """Validate a button with welcome-specific action semantics."""
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
        if "action" in comp:
            return False, f"{prefix} \u2014 link buttons must not have \"action\"."
        if "custom_id" in comp:
            return False, f"{prefix} \u2014 link buttons must not have \"custom_id\"."
    else:
        # Non-link buttons use named actions
        if "custom_id" in comp:
            return False, (
                f"{prefix} \u2014 has \"custom_id\" \u2014 use \"action\" instead. "
                f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}."
            )
        action = comp.get("action")
        if not isinstance(action, str) or not action:
            return False, f"{prefix} \u2014 action is required for non-link buttons."
        if action not in VALID_ACTIONS:
            return False, (
                f"{prefix} \u2014 action \"{action}\" is not a valid action. "
                f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}."
            )
        encoded = encode_custom_id(action, comp.get("params"))
        if len(encoded) > 100:
            return False, f"{prefix} \u2014 encoded custom_id exceeds 100 characters."
        if "url" in comp:
            return False, f"{prefix} \u2014 non-link buttons must not have \"url\"."

    return True, ""


def _validate_welcome_select(comp: Any, prefix: str) -> Tuple[bool, str]:
    """Validate a string select with welcome-specific option actions."""
    from utils.component_validators import validate_string_select
    return validate_string_select(comp, prefix, option_validator=_validate_welcome_select_option)


def _validate_welcome_select_option(opt: Any, prefix: str) -> Tuple[bool, str]:
    if not isinstance(opt, dict):
        return False, f"{prefix} \u2014 must be an object."

    label = opt.get("label")
    if not isinstance(label, str) or not label:
        return False, f"{prefix} \u2014 label must be a non-empty string."
    if len(label) > 100:
        return False, f"{prefix} \u2014 label exceeds 100 characters."

    action = opt.get("action")
    if not isinstance(action, str) or not action:
        return False, f"{prefix} \u2014 action is required."
    if action not in VALID_ACTIONS:
        return False, (
            f"{prefix} \u2014 action \"{action}\" is not a valid action. "
            f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}."
        )

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
