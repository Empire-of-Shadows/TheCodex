"""
Guide JSON Schema Validator

Validates the page-tree structure for the guide system.
Delegates component validation to the shared component_validators module.
Guide-specific button actions: "navigate", "channel", "role" with "target".

Error messages use human-readable paths:
  Page "Getting Started" → Action Row #1 → Button "Click Here" — target is required for navigate buttons.
"""

import json
import re
from typing import Any, Dict, List, Set, Tuple

from utils.component_validators import (
	trunc_label,
	validate_accent_color,
	validate_components_list,
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_MAX_LABEL = 100
_MAX_DESCRIPTION = 100
_MAX_DEPTH = 5  # TODO: make configurable via guild config (config.guide["max_depth"])
_VALID_BUTTON_STYLES = {"primary", "secondary", "success", "danger", "link"}
_VALID_GUIDE_ACTIONS = {"navigate", "channel", "role"}

# Hard ceiling on the serialized payload. Per-field limits bound a well-formed
# guide; this stops megabytes of junk in unrecognised keys from being stored
# verbatim. Guides nest deeper than welcome layouts, so the cap is larger.
_MAX_GUIDE_BYTES = 256 * 1024
_ALLOWED_TOP_LEVEL = {"accent_color", "pages"}


def validate_guide_schema(data: Any) -> Tuple[bool, str]:
	"""Validate a complete guide JSON config.

	Returns (True, "") on success or (False, human-readable error) on first failure.
	"""
	if not isinstance(data, dict):
		return False, "Top-level value must be a JSON object."

	try:
		size = len(json.dumps(data, default=str))
	except (TypeError, ValueError):
		return False, "Payload is not JSON-serializable."
	if size > _MAX_GUIDE_BYTES:
		return False, f"Guide payload is too large ({size} bytes; max {_MAX_GUIDE_BYTES})."

	unknown = set(data) - _ALLOWED_TOP_LEVEL
	if unknown:
		return False, f"Unknown top-level field(s): {', '.join(sorted(unknown))}."

	# Optional accent_color
	if "accent_color" in data:
		ok, msg = validate_accent_color(data["accent_color"])
		if not ok:
			return False, msg

	# Required pages
	if "pages" not in data:
		return False, "Missing required field: \"pages\"."
	pages = data["pages"]
	if not isinstance(pages, list) or len(pages) == 0:
		return False, "\"pages\" must be a non-empty array."

	# Collect all page IDs for uniqueness check and navigate target validation
	all_ids: Set[str] = set()
	navigate_targets: List[str] = []

	ok, msg = _validate_pages(pages, "", all_ids, navigate_targets, depth=0)
	if not ok:
		return False, msg

	# Validate navigate targets exist
	for target in navigate_targets:
		if target not in all_ids:
			return False, f"Navigate action targets page \"{target}\" which does not exist."

	return True, ""


def slugify(label: str) -> str:
	"""Convert a label to a URL-safe slug for use as a page ID."""
	slug = label.lower().strip()
	slug = re.sub(r"[^a-z0-9\s\-]", "", slug)
	slug = re.sub(r"[\s\-]+", "-", slug)
	slug = slug.strip("-")
	return slug or "page"


def normalize_pages(data: Dict[str, Any]) -> Dict[str, Any]:
	"""Auto-generate missing page IDs from labels and set default orders."""
	if "pages" not in data:
		return data

	_auto_id_pages(data["pages"], set())
	return data


def _auto_id_pages(pages: list, seen_ids: set, counter: list = None):
	"""Recursively assign IDs to pages that don't have one."""
	if counter is None:
		counter = [0]
	for i, page in enumerate(pages):
		if not isinstance(page, dict):
			continue
		if "id" not in page:
			label = page.get("label", "page")
			base_slug = slugify(label)
			slug = base_slug
			while slug in seen_ids:
				counter[0] += 1
				slug = f"{base_slug}-{counter[0]}"
			page["id"] = slug
		seen_ids.add(page["id"])
		if "order" not in page:
			page["order"] = i + 1
		if "children" in page and isinstance(page["children"], list):
			_auto_id_pages(page["children"], seen_ids, counter)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _page_label(page: Any, idx: int) -> str:
	"""Build a human-readable label for a page."""
	if isinstance(page, dict):
		label = page.get("label")
		if isinstance(label, str) and label:
			return f'Page "{trunc_label(label)}"'
	return f"Page #{idx + 1}"


# ─────────────────────────────────────────────────────────────────────────────
# Page tree validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_pages(
	pages: list,
	prefix: str,
	all_ids: Set[str],
	navigate_targets: List[str],
	depth: int,
) -> Tuple[bool, str]:
	if depth > _MAX_DEPTH:
		ctx = prefix or "Pages"
		return False, f"{ctx} \u2014 page nesting exceeds maximum depth of {_MAX_DEPTH}."

	for i, page in enumerate(pages):
		page_name = _page_label(page, i)
		page_prefix = f"{prefix} \u2192 {page_name}" if prefix else page_name
		ok, msg = _validate_page(page, page_prefix, all_ids, navigate_targets, depth)
		if not ok:
			return False, msg

	return True, ""


def _validate_page(
	page: Any,
	prefix: str,
	all_ids: Set[str],
	navigate_targets: List[str],
	depth: int,
) -> Tuple[bool, str]:
	if not isinstance(page, dict):
		return False, f"{prefix} \u2014 must be an object."

	# label (required)
	label = page.get("label")
	if not isinstance(label, str) or not label:
		return False, f"{prefix} \u2014 label must be a non-empty string."
	if len(label) > _MAX_LABEL:
		return False, f"{prefix} \u2014 label exceeds {_MAX_LABEL} characters."

	# id (optional, auto-generated)
	page_id = page.get("id")
	if page_id is not None:
		if not isinstance(page_id, str) or not page_id:
			return False, f"{prefix} \u2014 id must be a non-empty string."
		if len(page_id) > 100:
			return False, f"{prefix} \u2014 id exceeds 100 characters."
		if page_id in all_ids:
			return False, f"{prefix} \u2014 id \"{page_id}\" is duplicated. Page IDs must be unique."
		all_ids.add(page_id)
	else:
		# Generate and register
		generated = slugify(label)
		base = generated
		counter = 0
		while generated in all_ids:
			counter += 1
			generated = f"{base}-{counter}"
		all_ids.add(generated)

	# description (optional)
	desc = page.get("description")
	if desc is not None:
		if not isinstance(desc, str):
			return False, f"{prefix} \u2014 description must be a string."
		if len(desc) > _MAX_DESCRIPTION:
			return False, f"{prefix} \u2014 description exceeds {_MAX_DESCRIPTION} characters."

	# icon (optional)
	icon = page.get("icon")
	if icon is not None and not isinstance(icon, str):
		return False, f"{prefix} \u2014 icon must be a string."

	# order (optional)
	order = page.get("order")
	if order is not None and not isinstance(order, int):
		return False, f"{prefix} \u2014 order must be an integer."

	# content (optional)
	content = page.get("content")
	if content is not None:
		if not isinstance(content, dict):
			return False, f"{prefix} \u2014 content must be an object."
		components = content.get("components")
		if components is not None:
			ok, msg = validate_components_list(
				components,
				action_validator=lambda comp, pfx: _validate_guide_button(comp, pfx, navigate_targets),
				select_validator=lambda comp, pfx: _validate_guide_select(comp, pfx, navigate_targets),
			)
			if not ok:
				return False, f"{prefix} \u2192 {msg}"

	# children (optional)
	children = page.get("children")
	if children is not None:
		if not isinstance(children, list):
			return False, f"{prefix} \u2014 children must be an array."
		if len(children) > 25:
			return False, f"{prefix} \u2014 children has {len(children)} items; max is 25."
		ok, msg = _validate_pages(children, prefix, all_ids, navigate_targets, depth + 1)
		if not ok:
			return False, msg

	# Must have content or children (or both)
	if content is None and children is None:
		return False, f"{prefix} \u2014 must have \"content\", \"children\", or both."

	return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Guide-specific action validators
# ─────────────────────────────────────────────────────────────────────────────

def _validate_guide_button(comp: dict, prefix: str, navigate_targets: list) -> Tuple[bool, str]:
	"""Validate a button in guide context. Supports navigate, channel, role actions + link buttons."""
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
	else:
		action = comp.get("action")
		if not isinstance(action, str) or not action:
			return False, f"{prefix} \u2014 action is required for non-link buttons."
		if action not in _VALID_GUIDE_ACTIONS:
			return False, (
				f"{prefix} \u2014 action \"{action}\" is not valid. "
				f"Guide buttons support: {', '.join(sorted(_VALID_GUIDE_ACTIONS))}."
			)
		target = comp.get("target")
		if not isinstance(target, str) or not target:
			return False, f"{prefix} \u2014 target is required for {action} buttons."
		if action == "navigate":
			navigate_targets.append(target)

	return True, ""


def _validate_guide_select(comp: Any, prefix: str, navigate_targets: list) -> Tuple[bool, str]:
	"""Validate a string select in guide context."""
	from utils.component_validators import validate_string_select
	return validate_string_select(
		comp, prefix,
		option_validator=lambda opt, pfx: _validate_guide_select_option(opt, pfx, navigate_targets),
	)


def _validate_guide_select_option(opt: Any, prefix: str, navigate_targets: list) -> Tuple[bool, str]:
	if not isinstance(opt, dict):
		return False, f"{prefix} \u2014 must be an object."

	label = opt.get("label")
	if not isinstance(label, str) or not label:
		return False, f"{prefix} \u2014 label must be a non-empty string."
	if len(label) > 100:
		return False, f"{prefix} \u2014 label exceeds 100 characters."

	action = opt.get("action")
	if action not in _VALID_GUIDE_ACTIONS:
		return False, (
			f"{prefix} \u2014 action \"{action}\" is not valid. "
			f"Guide select options support: {', '.join(sorted(_VALID_GUIDE_ACTIONS))}."
		)

	target = opt.get("target")
	if not isinstance(target, str) or not target:
		return False, f"{prefix} \u2014 target is required for {action} options."
	if action == "navigate":
		navigate_targets.append(target)

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
