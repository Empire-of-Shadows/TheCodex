"""
Color Set Resolution Algorithm — pure functions, no DB calls.

Always-additive model: a user's final color pool is the union of all color
sets assigned to their roles and tiers via embed_role_tier_mapping.

There is no priority ordering, no override mode, and no tie-breaking —
every applicable color set contributes its colors to the pool.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ColorAssignment:
    """Expanded representation of a single color-set assignment."""
    color_set_id: str
    source_type: str    # "role" | "tier"
    source_id: str      # role_id str or tier_name
    colors: list[int]   # pre-fetched color ints for this set


# ── Resolution algorithm ───────────────────────────────────────────────────────

def resolve_colors(assignments: list[ColorAssignment]) -> list[int]:
    """Return the final list of allowed Discord color integers.

    Always-additive: union of all color sets from all applicable assignments.
    Deduplicates by hex value (color int).

    Args:
        assignments: All ColorAssignments applicable to a specific user context.

    Returns:
        Deduplicated list of allowed color ints.
    """
    if not assignments:
        return []

    pool: dict[int, None] = {}
    for assignment in assignments:
        for color in assignment.colors:
            pool[color] = None

    return list(pool.keys())
