"""
Embed Config constants shared by the admin panel.

Tier names/labels and feature-access options consumed by the generic panel
engine (panel_engine.py / panel_configs.py). Role Tier Mapping and Feature
Access views have been migrated to the generic panel engine; Color Tiers have
been replaced by the Color Set system (color_views.py).
"""


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
