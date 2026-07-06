"""
Guide Action Registry & Dispatcher

Named action system for guide component interactions.
All custom_ids use the "g:" prefix to avoid collisions with the welcome system ("w:").
"""

import discord
from storage.logging import get_logger

logger = get_logger("GuideActions")

_PREFIX = "g"


# ─────────────────────────────────────────────────────────────────────────────
# Custom ID Encoding / Decoding
# ─────────────────────────────────────────────────────────────────────────────

def encode_nav(page_id: str) -> str:
	"""Encode a page navigation into a custom_id: ``g:nav:<page_id>``."""
	return f"{_PREFIX}:nav:{page_id}"


def encode_channel(channel_id: str) -> str:
	"""Encode a channel link action: ``g:channel:<channel_id>``."""
	return f"{_PREFIX}:channel:{channel_id}"


def encode_role(role_id: str) -> str:
	"""Encode a role grant action: ``g:role:<role_id>``."""
	return f"{_PREFIX}:role:{role_id}"


def encode_action(action: str) -> str:
	"""Encode a simple action: ``g:<action>``."""
	return f"{_PREFIX}:{action}"


def decode_custom_id(raw: str) -> tuple[str | None, str | None]:
	"""Decode a custom_id string into (action, target).

	Returns:
		("nav", page_id)       for g:nav:<page_id>
		("channel", channel_id) for g:channel:<channel_id>
		("role", role_id)       for g:role:<role_id>
		("back", None)         for g:back
		("home", None)         for g:home
		("search", None)       for g:search
		("_select", None)      for g:_select  (value carries the page_id)
		("_uselect", None)     for g:_uselect (user-defined select)
		(None, None)           if not a guide custom_id
	"""
	if not raw.startswith(f"{_PREFIX}:"):
		return None, None
	rest = raw[len(_PREFIX) + 1:]

	if rest.startswith("nav:"):
		return "nav", rest[4:]
	if rest.startswith("channel:"):
		return "channel", rest[8:]
	if rest.startswith("role:"):
		return "role", rest[5:]
	if rest in ("back", "home", "search", "_select", "_uselect"):
		return rest, None

	return None, None


def decode_select_value(value: str) -> tuple[str, str]:
	"""Decode a user-defined select option value.

	Values are encoded as ``action:target``, e.g. ``nav:page-id``, ``channel:123``, ``role:456``.

	Returns:
		(action, target) — e.g. ("nav", "page-id"), ("channel", "123456"), ("role", "789")
	"""
	if ":" in value:
		action, target = value.split(":", 1)
	else:
		action, target = "nav", value
	# The builder emits "navigate" for page links; the dispatcher speaks "nav".
	if action == "navigate":
		action = "nav"
	return action, target


def encode_select_value(action: str, target: str) -> str:
	"""Encode an action+target into a select option value string."""
	return f"{action}:{target}"


# Constants for well-known custom_ids
CUSTOM_ID_BACK = encode_action("back")
CUSTOM_ID_HOME = encode_action("home")
CUSTOM_ID_SEARCH = encode_action("search")
CUSTOM_ID_SELECT = encode_action("_select")
CUSTOM_ID_USELECT = encode_action("_uselect")
CUSTOM_ID_SECTIONS = encode_action("_sections")
