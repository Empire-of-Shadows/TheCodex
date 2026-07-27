"""
Info Board Schema Validator

Validates the JSON config for the info board builder. All validation is
synchronous and returns (bool, str) - success or the first error.

Structural component validation is delegated to the shared component_validators
module. What is board-specific:

  - a board carries a pool of named ``responses``, each its own components layout
  - buttons and select options carry ``action`` + ``target`` (reply / channel / role)
  - every ``reply`` target must resolve to a response that actually exists

Because responses are validated with the same component rules as the board itself,
a response can carry its own buttons pointing at other responses - nesting comes
free and is validated by the same reference check.
"""

import json
import re
from typing import Any, Dict, Set, Tuple

from Features.Board.board_actions import VALID_ACTIONS, encode_custom_id
from utils.component_validators import (
    validate_accent_color,
    validate_components_list,
    validate_string_select,
)
from utils.safe_content import check_no_dangerous_content

_VALID_BUTTON_STYLES = {"primary", "secondary", "success", "danger", "link"}

# Hard ceiling on the serialized payload. The per-field limits already bound a
# well-formed board; this stops a caller smuggling megabytes of junk through
# unrecognised keys. A board holds a message plus its responses, so it gets more
# room than a greeting (64 KB) but less than a whole guide tree (256 KB).
_MAX_BOARD_BYTES = 128 * 1024

_ALLOWED_TOP_LEVEL = {"accent_color", "components", "responses"}
_ALLOWED_RESPONSE_KEYS = {"id", "label", "accent_color", "components"}

_MAX_RESPONSES = 25

# Response ids are slugs. The cap keeps ``b:r:<id>`` inside Discord's 100-character
# custom_id limit with room to spare; the charset keeps ids free of the ":" the
# encoding uses as a separator.
_RESPONSE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

# Discord's hard limit on a component custom_id.
_MAX_CUSTOM_ID = 100


def validate_board_schema(data: Any) -> Tuple[bool, str]:
    """Validate an info board JSON config dict.

    Returns (True, "") on success or (False, human-readable error) on first failure.
    """
    if not isinstance(data, dict):
        return False, "Top-level value must be a JSON object."

    try:
        size = len(json.dumps(data, default=str))
    except (TypeError, ValueError):
        return False, "Payload is not JSON-serializable."
    if size > _MAX_BOARD_BYTES:
        return False, f"Board payload is too large ({size} bytes; max {_MAX_BOARD_BYTES})."

    unknown = set(data) - _ALLOWED_TOP_LEVEL
    if unknown:
        return False, f"Unknown top-level field(s): {', '.join(sorted(unknown))}."

    if "accent_color" in data:
        ok, msg = validate_accent_color(data["accent_color"])
        if not ok:
            return False, msg

    if "components" not in data:
        return False, "Missing required field: \"components\"."

    # Collect the response ids first so the board's own buttons can be checked
    # against them in the same pass.
    ok, msg, response_ids = _collect_response_ids(data.get("responses"))
    if not ok:
        return False, msg

    ok, msg = validate_components_list(
        data["components"],
        action_validator=_button_validator(response_ids),
        select_validator=_select_validator(response_ids),
    )
    if not ok:
        return False, msg

    # Each response is a components layout in its own right, validated with the
    # same rules - including its references back into the response pool.
    for i, response in enumerate(data.get("responses") or []):
        prefix = f"Response \"{response.get('id')}\"" if response.get("id") else f"Response #{i + 1}"
        ok, msg = validate_components_list(
            response["components"],
            action_validator=_button_validator(response_ids),
            select_validator=_select_validator(response_ids),
        )
        if not ok:
            return False, f"{prefix} -> {msg}"

    # Content-safety scan runs last so structural errors keep their specific messages.
    return check_no_dangerous_content(data)


# ─────────────────────────────────────────────────────────────────────────────
# Response pool
# ─────────────────────────────────────────────────────────────────────────────

def _collect_response_ids(responses: Any) -> Tuple[bool, str, Set[str]]:
    """Validate the response pool's own structure and return the set of ids."""
    if responses is None:
        return True, "", set()
    if not isinstance(responses, list):
        return False, "\"responses\" must be an array.", set()
    if len(responses) > _MAX_RESPONSES:
        return False, f"responses has {len(responses)} items; max is {_MAX_RESPONSES}.", set()

    ids: Set[str] = set()
    for i, response in enumerate(responses):
        prefix = f"Response #{i + 1}"
        if not isinstance(response, dict):
            return False, f"{prefix} - must be an object.", set()

        unknown = set(response) - _ALLOWED_RESPONSE_KEYS
        if unknown:
            return False, f"{prefix} - unknown field(s): {', '.join(sorted(unknown))}.", set()

        rid = response.get("id")
        if not isinstance(rid, str) or not rid:
            return False, f"{prefix} - id must be a non-empty string.", set()
        if not _RESPONSE_ID_RE.match(rid):
            return False, (
                f"{prefix} - id \"{rid}\" is invalid. Use lowercase letters, digits, "
                f"hyphens and underscores, starting with a letter or digit, max 48 characters."
            ), set()
        if rid in ids:
            return False, f"{prefix} - duplicate response id \"{rid}\".", set()

        # Belt and braces: the regex already bounds this, but measure the real
        # encoded string so the limit can never drift away from the encoder.
        encoded = encode_custom_id("reply", rid)
        if len(encoded) > _MAX_CUSTOM_ID:
            return False, (
                f"{prefix} - id \"{rid}\" makes a custom_id of {len(encoded)} "
                f"characters; max is {_MAX_CUSTOM_ID}."
            ), set()

        label = response.get("label")
        if label is not None:
            if not isinstance(label, str):
                return False, f"{prefix} - label must be a string.", set()
            if len(label) > 100:
                return False, f"{prefix} - label exceeds 100 characters.", set()

        if "accent_color" in response:
            ok, msg = validate_accent_color(response["accent_color"])
            if not ok:
                return False, f"{prefix} - {msg}", set()

        if "components" not in response:
            return False, f"{prefix} - missing required field: \"components\".", set()

        ids.add(rid)

    return True, "", ids


# ─────────────────────────────────────────────────────────────────────────────
# Board-specific action validators
# ─────────────────────────────────────────────────────────────────────────────

def _button_validator(response_ids: Set[str]):
    def _validate(comp: dict, prefix: str) -> Tuple[bool, str]:
        return _validate_board_button(comp, prefix, response_ids)
    return _validate


def _select_validator(response_ids: Set[str]):
    def _validate(comp: Any, prefix: str) -> Tuple[bool, str]:
        return validate_string_select(
            comp, prefix,
            option_validator=lambda opt, p: _validate_board_option(opt, p, response_ids),
        )
    return _validate


def _validate_board_button(comp: dict, prefix: str, response_ids: Set[str]) -> Tuple[bool, str]:
    """Validate a button with board action semantics."""
    if not isinstance(comp, dict):
        return False, f"{prefix} - must be an object."

    style = comp.get("style")
    if style not in _VALID_BUTTON_STYLES:
        return False, (
            f"{prefix} - style \"{style}\" is invalid. "
            f"Valid styles: {', '.join(sorted(_VALID_BUTTON_STYLES))}."
        )

    label = comp.get("label")
    if not isinstance(label, str) or not label:
        return False, f"{prefix} - label must be a non-empty string."
    if len(label) > 80:
        return False, f"{prefix} - label exceeds 80 characters."

    if style == "link":
        url = comp.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            return False, f"{prefix} - url is required for link buttons and must start with https://."
        for forbidden in ("action", "target", "custom_id"):
            if forbidden in comp:
                return False, f"{prefix} - link buttons must not have \"{forbidden}\"."
        return True, ""

    if "custom_id" in comp:
        return False, (
            f"{prefix} - has \"custom_id\" - use \"action\" and \"target\" instead. "
            f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}."
        )
    if "url" in comp:
        return False, f"{prefix} - non-link buttons must not have \"url\"."

    return _validate_action_target(comp, prefix, response_ids)


def _validate_board_option(opt: Any, prefix: str, response_ids: Set[str]) -> Tuple[bool, str]:
    """Validate a select option with board action semantics."""
    if not isinstance(opt, dict):
        return False, f"{prefix} - must be an object."

    label = opt.get("label")
    if not isinstance(label, str) or not label:
        return False, f"{prefix} - label must be a non-empty string."
    if len(label) > 100:
        return False, f"{prefix} - label exceeds 100 characters."

    description = opt.get("description")
    if description is not None:
        if not isinstance(description, str):
            return False, f"{prefix} - description must be a string."
        if len(description) > 100:
            return False, f"{prefix} - description exceeds 100 characters."

    emoji = opt.get("emoji")
    if emoji is not None and not isinstance(emoji, str):
        return False, f"{prefix} - emoji must be a string."

    return _validate_action_target(opt, prefix, response_ids)


def _validate_action_target(
    comp: Dict[str, Any], prefix: str, response_ids: Set[str]
) -> Tuple[bool, str]:
    """Validate the shared action/target pair used by board buttons and options."""
    action = comp.get("action")
    if not isinstance(action, str) or not action:
        return False, (
            f"{prefix} - action is required. "
            f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}."
        )
    if action not in VALID_ACTIONS:
        return False, (
            f"{prefix} - action \"{action}\" is not a valid action. "
            f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}."
        )

    target = comp.get("target")
    if not isinstance(target, str) or not target:
        return False, f"{prefix} - target is required for the \"{action}\" action."

    if action == "reply":
        if target not in response_ids:
            known = ", ".join(sorted(response_ids)) if response_ids else "none defined"
            return False, (
                f"{prefix} - points at response \"{target}\", which does not exist. "
                f"Known responses: {known}."
            )
    else:
        # channel and role targets are Discord snowflakes.
        if not target.isdigit():
            return False, (
                f"{prefix} - target for the \"{action}\" action must be a "
                f"Discord ID (digits only)."
            )

    encoded = encode_custom_id(action, target)
    if len(encoded) > _MAX_CUSTOM_ID:
        return False, f"{prefix} - encoded custom_id exceeds {_MAX_CUSTOM_ID} characters."

    return True, ""
