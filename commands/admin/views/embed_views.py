"""
Embed Config Views using Discord Components v2.

Panel views for managing embed configuration (description limits,
feature access, status overview).

Note: Role Tier Mapping and Feature Access views have been migrated
to the generic panel engine (panel_engine.py / panel_configs.py).
Color Tiers have been replaced by the Color Set system (color_views.py).
"""

import discord

from .base import AdminLayoutBuilder, readonly_container


# ── Tier Names ────────────────────────────────────────────────────────────
TIER_NAMES = ["tier_1", "tier_2", "tier_3", "tier_4", "tier_5"]
TIER_LABELS = {
    "tier_1": "Tier 1",
    "tier_2": "Tier 2",
    "tier_3": "Tier 3",
    "tier_4": "Tier 4",
    "tier_5": "Tier 5",
}


# ── Feature Access constants ──────────────────────────────────────────

FEATURE_OPTIONS = [
    ("basic_embed", "Basic Embed", "Create basic embeds with title and description"),
    ("image_field", "Image Field", "Add images and thumbnails"),
    ("author_field", "Author Field", "Add author name and icon"),
    ("footer_field", "Footer Field", "Add footer text"),
    ("timestamp", "Timestamp", "Add timestamps to embeds"),
]

_FEATURE_LABEL_MAP = {key: label for key, label, _ in FEATURE_OPTIONS}


# ── Status View ──────────────────────────────────────────────────────

def build_embed_status_view(stats: dict, guild: discord.Guild) -> discord.ui.LayoutView:
    """Build a detailed read-only status overview of embed configuration."""
    builder = AdminLayoutBuilder()

    builder.add_header("## Embed Configuration Status")

    # ── Role Tier Mapping ──────────────────────────────────────────────────
    tier_roles: dict = stats.get("tier_roles", {})
    mapping_lines = []
    for t in TIER_NAMES:
        role_ids = tier_roles.get(t, [])
        if role_ids:
            names = []
            for rid in role_ids:
                role = guild.get_role(rid)
                names.append(f"<@&{rid}>" if role else f"Unknown ({rid})")
            mapping_lines.append(f"- **{TIER_LABELS[t]}:** {', '.join(names)}")
        else:
            mapping_lines.append(f"- **{TIER_LABELS[t]}:** *Not assigned*")

    # ── Description Limits ─────────────────────────────────────────────────
    default_limit = stats.get("default_limit", 500)
    tier_limits: dict = stats.get("tier_limits", {})
    limit_lines = [f"**Default:** {default_limit} characters"]
    for t in TIER_NAMES:
        if t in tier_limits:
            limit_lines.append(f"- **{TIER_LABELS[t]}:** {tier_limits[t]} characters")
    if len(limit_lines) == 1:
        limit_lines.append("*No tier-specific limits set*")

    # ── Color Sets ─────────────────────────────────────────────────────────
    color_sets: list = stats.get("color_sets", [])
    cs_text = ""
    if color_sets:
        cs_lines = []
        for cs in color_sets:
            assign_parts = []
            for a in cs.get("assignments", []):
                if a.get("target_type") == "tier":
                    assign_parts.append(TIER_LABELS.get(a["target_id"], a["target_id"]))
                else:
                    tid = str(a.get("target_id", ""))
                    role = guild.get_role(int(tid)) if tid.isdigit() else None
                    assign_parts.append(f"<@&{tid}>" if role else f"role:{tid}")
            assign_str = ", ".join(assign_parts) if assign_parts else "Unassigned"
            cs_lines.append(f"- **{cs['name']}** — {cs['color_count']} color(s) · {assign_str}")
        cs_text = "\n".join(cs_lines)
    else:
        cs_text = "*No color sets configured*"

    # ── Feature Access ─────────────────────────────────────────────────────
    feature_access: dict = stats.get("feature_access", {})
    fa_text = ""
    if feature_access:
        feat_lines = []
        for key, tier_names in feature_access.items():
            label = _FEATURE_LABEL_MAP.get(key, key)
            tiers_str = ", ".join(TIER_LABELS.get(t, t) for t in tier_names)
            feat_lines.append(f"- **{label}:** {tiers_str}")
        fa_text = "\n".join(feat_lines)
    else:
        fa_text = "*No features configured*"

    body = (
        f"**Server:** {guild.name}\n\n"
        f"**Role Tier Mapping**\n" + "\n".join(mapping_lines) + "\n\n"
        f"**Description Limits**\n" + "\n".join(limit_lines) + "\n\n"
        f"**Color Sets**\n" + cs_text + "\n\n"
        f"**Feature Access**\n" + fa_text
    )
    builder.add_item(readonly_container(discord.ui.TextDisplay(body)))

    return builder.build()
