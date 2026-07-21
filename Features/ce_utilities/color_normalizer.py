"""
Color normalization utilities for the Color Set system.

Converts user-provided color input (hex or rgb) to Discord color integers and back.
All internal storage uses Discord color ints (0x000000-0xFFFFFF).

Supported input formats:
  - Hex: "#FFAA00", "FFAA00", "#FA0" (3-digit shorthand expands to 6)
  - RGB function: "rgb(255, 170, 0)"
"""

import re


def normalize_color(raw: str) -> int | None:
    """Normalize a hex or rgb color input to a Discord color integer.

    Accepts:
    - Hex with/without #: "#FFAA00", "FFAA00", "#FA0"
    - RGB function: "rgb(255, 170, 0)"

    Returns None if the input cannot be parsed.
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    # Hex with or without #: 3 or 6 hex chars
    hex_match = re.match(r'^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$', raw)
    if hex_match:
        h = hex_match.group(1)
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        return int(h, 16)

    # RGB function: rgb(255, 170, 0)
    rgb_fn = re.match(
        r'^rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$',
        raw, re.IGNORECASE
    )
    if rgb_fn:
        r, g, b = int(rgb_fn.group(1)), int(rgb_fn.group(2)), int(rgb_fn.group(3))
        if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
            return (r << 16) | (g << 8) | b
        return None

    return None


def color_int_to_hex(color_int: int) -> str:
    """Convert a Discord color integer to a #RRGGBB hex string."""
    return f"#{color_int:06X}"


def parse_named_colors_string(raw: str) -> tuple[list[dict], list[str]]:
    """Parse a multi-line named color input into a list of named color dicts.

    Each line should be in the format:
        Display Name: #RRGGBB
        Display Name: rgb(r, g, b)

    Lines without a colon are treated as a bare color code; the code itself
    becomes the display name (e.g. "#FF0000" → name="#FF0000").

    Duplicate values (same color int, different names) are silently skipped -
    the first occurrence wins.

    Returns:
        (named_colors, failed_lines) where named_colors is a deduplicated
        list of {"name": str, "value": int} dicts and failed_lines contains
        the raw text of any lines that could not be parsed.
    """
    results: list[dict] = []
    failed: list[str] = []
    seen_values: set[int] = set()

    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        if ':' in line:
            # Split on the first colon only (rgb() has no colon inside)
            split_idx = line.index(':')
            name = line[:split_idx].strip()
            code = line[split_idx + 1:].strip()
        else:
            name = line
            code = line

        if not name:
            name = code

        color_val = normalize_color(code)
        if color_val is not None:
            if color_val not in seen_values:
                seen_values.add(color_val)
                results.append({"name": name, "value": color_val})
            # Silently skip duplicates (same value, different name)
        else:
            failed.append(line)

    return results, failed
