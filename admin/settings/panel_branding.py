"""
Admin panel branding text for TheCodex.

NOTE: the admin-panel engine does NOT import this file. It reads branding only through the
seam -- ``bindings.py`` re-exports the strings the engine consumes (SETUP_GUIDE_TEXT,
OVERVIEW_FOOTER), which the engine imports from ``.settings.bindings``. Keeping these strings
in a separate module is a codex-side organizational choice; a bot may equally inline them in
``bindings.py`` (relay does). Empty string for unused fields.

Fields (re-exported through bindings.py):
    SETUP_GUIDE_TEXT:   Quick-setup guidance shown above the overview.
    PANEL_TITLE:        Title rendered at the top of the master panel.
    PANEL_DESCRIPTION:  Short description shown beneath PANEL_TITLE.
    OVERVIEW_FOOTER:    Optional tagline/footer text. Empty string disables it.
"""

SETUP_GUIDE_TEXT = (
    "**Quick Setup Guide**\n"
    "Configure these areas in order - later features depend on the earlier ones.\n"
    "\n"
    "**1. Role Configuration**"
    "Give users permission to open the admin panel.\n"
    "- Set **Panel Access Roles** so trusted members can open this panel without "
    "Manage Server.\n"
    "- Optionally set **Mod Access Roles** for limited (mod-tier) access.\n"
    "\n"
    "**2. Embed Settings**"
    "Control who can create embeds and what they look like.\n"
    "- Map roles to embed color tiers under **Role Tier Mapping** first; the rest "
    "of Embed Settings unlocks once tiers are mapped.\n"
    "- Optionally adjust **Description Limits**, **Color Tiers**, and "
    "**Feature Access**.\n"
    "\n"
    "**3. Feature Channels**"
    "Pick where each feature posts in your server.\n"
    "- **WYR Channel** - required before any WYR sub-setting unlocks.\n"
    "- **Welcome Channel** - required before New Members sub-settings unlock.\n"
    "- **Drops Channel**, **Announcement Channel**, **Suggestion Channel**, "
    "**Guide Channel** - set per feature you want enabled.\n"
    "\n"
    "**4. Feature Tuning**"
    "Fine-tune each feature's behavior once its channel is set.\n"
    "- Open each feature group below to tune schedules, ping roles, thread "
    "behavior, whitelist roles, and JSON layouts.\n"
    "\n"
    "Toggle **Show Config Details** below to see the current value of every "
    "setting at a glance."
)

PANEL_TITLE = "Server Configuration"

PANEL_DESCRIPTION = "Configure TheCodex bot settings for this server."

OVERVIEW_FOOTER = ""
