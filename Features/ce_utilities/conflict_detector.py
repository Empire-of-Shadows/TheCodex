"""
Conflict Detector for the Color Set system.

Validates proposed Color Set changes before they are persisted.

The system is always-additive; the only hard constraints are:

  BREAKING:
    - A hex value already exists in another color set in the guild
      (cross-set color uniqueness — checked on add).
    - A color set is already assigned to a different tier
      (tier exclusivity — one set can be in at most one tier).

All conflicts in this module are BREAKING (hard blocks — no confirmation
prompts needed).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class ConflictResult:
    status: str                         # "ok" | "breaking"
    message: str                        # Human-readable explanation
    affected_entities: list[str] = field(default_factory=list)


# ── Public API ─────────────────────────────────────────────────────────────────

async def check_color_uniqueness(
    guild_id: int,
    colors: list[dict],
    exclude_set_id: str | None = None,
) -> ConflictResult:
    """Check if any proposed color hex already exists in another set in the guild.

    Cross-set color uniqueness: a color hex value cannot appear in more than
    one color set per guild.  Adding a duplicate is always blocked.

    Args:
        guild_id:        Target guild.
        colors:          Proposed colors as list[{"name": str, "value": int}].
        exclude_set_id:  The set being modified — excluded from the comparison
                         so that existing colors in the same set are not flagged.

    Returns:
        ConflictResult with status "ok" or "breaking".
    """
    # Late import to avoid circular dependency at module level.
    from admin.actions.color_set_actions import ColorSetActions
    from Features.ce_utilities.color_normalizer import color_int_to_hex

    try:
        all_sets = await ColorSetActions.list_color_sets(guild_id)
    except Exception:
        return ConflictResult(status="ok", message="Could not verify uniqueness — proceeding.")

    proposed_values = {c["value"] for c in colors}

    for s in all_sets:
        if exclude_set_id and s["set_id"] == exclude_set_id:
            continue
        for c in s.get("colors", []):
            val = c["value"] if isinstance(c, dict) else c
            if val in proposed_values:
                hex_str = color_int_to_hex(val)
                return ConflictResult(
                    status="breaking",
                    message=(
                        f"Color `{hex_str}` already exists in set **{s['name']}**. "
                        f"Remove it there first."
                    ),
                    affected_entities=[hex_str],
                )

    return ConflictResult(status="ok", message="No conflicts detected.")


async def check_tier_exclusivity(
    guild_id: int,
    color_set_id: str,
    proposed_tier: str,
) -> ConflictResult:
    """Check if this color set is already assigned to a different tier.

    A color set can be assigned to at most one tier.  Assigning to the same
    tier again is idempotent (returns "ok").

    Args:
        guild_id:       Target guild.
        color_set_id:   The color set being assigned.
        proposed_tier:  The tier being assigned to (e.g. "tier_1").

    Returns:
        ConflictResult with status "ok" or "breaking".
    """
    from admin.actions.color_set_actions import ColorSetActions

    try:
        assignments = await ColorSetActions.list_assignments(guild_id, set_id=color_set_id)
    except Exception:
        return ConflictResult(status="ok", message="Could not verify tier exclusivity — proceeding.")

    for a in assignments:
        if a.get("target_type") == "tier" and a.get("target_id") != proposed_tier:
            existing_tier = a["target_id"]
            existing_label = existing_tier.replace("_", " ").title()
            proposed_label = proposed_tier.replace("_", " ").title()
            return ConflictResult(
                status="breaking",
                message=(
                    f"This set is already assigned to **{existing_label}**. "
                    f"Remove that assignment first before assigning to {proposed_label}."
                ),
                affected_entities=[existing_tier],
            )

    return ConflictResult(status="ok", message="No tier exclusivity conflict.")
