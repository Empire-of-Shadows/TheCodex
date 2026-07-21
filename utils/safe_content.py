"""
Content-safety scan - shared guard against payloads that pass the structural
schema but are "not what we intend to be uploaded".

Mirror of dashboard/frontend/src/validators/safeContent.ts (keep the two in sync).
Applied to every guide and welcome payload after structural validation.

Rejects:
  - Prototype-pollution key names anywhere in the object tree
    (__proto__/constructor/prototype).
  - Unsafe HTML / script markup in any string (<script>, <img onerror=...>,
    <svg onload=...>, ...). The tag list omits short names that collide with
    Discord mention syntax (<@id>, <#id>, <:emoji:>, <a:emoji:>, </cmd:id>, <t:ts>),
    and allows ordinary markdown / mentions / non-Latin scripts.
  - Invisible / bidirectional control characters used for spoofing (Trojan Source).
"""

import re
from typing import Any, Tuple

_DANGEROUS_KEYS = {"__proto__", "constructor", "prototype"}

# Invisible / bidi control chars. Deliberately EXCLUDES U+200C/U+200D (ZWNJ/ZWJ) -
# those are required by emoji sequences and scripts like Persian and Indic.
_INVISIBLE_CTRL = re.compile("[\u00AD\u200B\u200E\u200F\u202A-\u202E\u2060\u2066-\u2069\uFEFF]")

# Unsafe HTML tags (opening or closing). Multi-character, non-colliding names only.
_UNSAFE_HTML_TAG = re.compile(
    r"<\s*/?\s*(?:script|style|iframe|object|embed|svg|img|link|meta|base|video|"
    r"audio|source|math|template|xml|noscript|frame|frameset|applet)\b",
    re.IGNORECASE,
)
# Inline event handlers: onerror=, onload=, onclick=, onmouseover=, ...
_EVENT_HANDLER = re.compile(r"(?:^|[\s/;])on[a-z]{3,}\s*=", re.IGNORECASE)
# Dangerous URL schemes.
_DANGEROUS_SCHEME = re.compile(
    r"(?:javascript|vbscript)\s*:|data\s*:\s*text/html", re.IGNORECASE
)


def check_safe_string(value: str, path: str) -> Tuple[bool, str]:
    """Check a single string for unsafe markup / control characters."""
    if _INVISIBLE_CTRL.search(value):
        return False, f"{path} contains a disallowed invisible or bidirectional control character."
    if _UNSAFE_HTML_TAG.search(value) or _EVENT_HANDLER.search(value) or _DANGEROUS_SCHEME.search(value):
        return False, f"{path} contains disallowed HTML or script markup."
    return True, ""


def check_no_dangerous_content(value: Any, path: str = "value") -> Tuple[bool, str]:
    """Recursively scan a parsed JSON value.

    Returns (True, "") if clean, or (False, message) on the first violation. `path`
    builds a human-readable location, e.g. ``pages[0].content.components[1].content``.
    """
    if isinstance(value, str):
        return check_safe_string(value, path)
    if isinstance(value, list):
        for i, item in enumerate(value):
            ok, msg = check_no_dangerous_content(item, f"{path}[{i}]")
            if not ok:
                return False, msg
        return True, ""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _DANGEROUS_KEYS:
                return False, f'{path} contains a disallowed property name "{key}".'
            child_path = key if path == "value" else f"{path}.{key}"
            ok, msg = check_no_dangerous_content(child, child_path)
            if not ok:
                return False, msg
    return True, ""
