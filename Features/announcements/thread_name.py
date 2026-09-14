"""Announcement thread name format: validation and safe rendering.

The format is typed by an admin (panel or dashboard) and rendered with
``str.format``. Saved unchecked, an unknown placeholder or a stray brace raised on
every announcement and silently stopped all discussion threads. Both write paths
now validate with :func:`thread_name_format_error`, and the listener renders
through :func:`render_thread_name`, which falls back to the default format for any
value already stored before validation existed.

Dependency-free on purpose: the dashboard imports it too.
"""

from __future__ import annotations

from string import Formatter

DEFAULT_THREAD_NAME_FORMAT = "💬 {message_content}"
ALLOWED_PLACEHOLDERS = ("message_content", "author_name", "channel_name")


def thread_name_format_error(fmt: str | None) -> str | None:
    """Return a member-readable error for an unusable format, or None when it is fine."""
    if fmt is None or not str(fmt).strip():
        return "The thread name format cannot be empty."
    allowed = ", ".join("{" + name + "}" for name in ALLOWED_PLACEHOLDERS)
    try:
        fields = [field for _, field, _, _ in Formatter().parse(str(fmt)) if field is not None]
    except ValueError:
        return (
            "The format has an unmatched { or }. Use only these placeholders: "
            f"{allowed}. To show a brace itself, type it twice."
        )
    unknown = sorted({f for f in fields if f not in ALLOWED_PLACEHOLDERS})
    if unknown:
        named = ", ".join("{" + (f or "") + "}" for f in unknown)
        return f"Unknown placeholder {named}. Use only these placeholders: {allowed}."
    return None


def render_thread_name(fmt: str | None, *, message_content: str, author_name: str,
                       channel_name: str) -> str:
    """Render a thread name, falling back to the default format if ``fmt`` is unusable."""
    values = {
        "message_content": message_content,
        "author_name": author_name,
        "channel_name": channel_name,
    }
    if thread_name_format_error(fmt) is not None:
        fmt = DEFAULT_THREAD_NAME_FORMAT
    return str(fmt).format(**values)
