"""
Admin Panel Views using Discord Components v2.

Contains the main panel and subcategory menu layouts for admin configuration.
Two-level navigation: top-level groups -> sub-options within each group.
"""

import discord
from typing import Callable, Awaitable

from .base import create_unique_id


# Top-level groups shown in the first dropdown
PANEL_GROUPS = [
    ("embed_settings", "Embed Settings", "Configure embed colors, tiers, limits, and features"),
    ("wyr_settings", "WYR Settings", "Configure Would You Rather scheduling and behavior"),
    ("new_members", "New Members", "Configure welcome messages, account age, and whitelist"),
    ("trackers", "Trackers", "Configure boost tracker and tag tracker"),
    ("updates_drops", "Updates & Drops", "Configure drops channel and tracked channels"),
    ("announcements", "Announcements", "Configure announcement thread auto-creation"),
    ("suggestions", "Suggestions", "Configure suggestion channel and view stats"),
    ("guide_settings", "Guide", "Configure the server guide system"),
]

# Sub-categories within each group
PANEL_SUBCATEGORIES = {
    "embed_settings": [
        ("role_tiers", "Role Tier Mapping", "Map roles to embed color tiers"),
        ("description_limits", "Description Limits", "Set per-tier embed description limits"),
        ("color_tiers", "Color Tiers", "Manage per-guild color palettes"),
        ("feature_access", "Feature Access", "Control which tier can use embed features"),
        ("status", "View Status", "View embed configuration summary"),
    ],
    "wyr_settings": [
        ("wyr_channel", "WYR Channel", "Set the WYR posting channel"),
        ("wyr_ping_role", "WYR Ping Role", "Set the role pinged when WYR posts"),
        ("wyr_schedule", "WYR Schedule", "Set daily WYR post time and timezone"),
        ("wyr_category", "WYR Category", "Set default question category"),
        ("wyr_thread", "WYR Thread Settings", "Configure discussion thread behavior"),
        ("wyr_cleanup", "WYR Cleanup", "Set mapping cleanup period"),
        ("wyr_status", "WYR Status", "View WYR configuration summary"),
    ],
    "new_members": [
        ("nm_welcome_channel", "Welcome Channel", "Set the channel for welcome messages"),
        ("nm_welcome_builder", "Welcome Message Builder", "Upload a JSON layout for the welcome message"),
        ("nm_settings", "General Settings", "Account age, auto-kick, and toggles"),
        ("nm_whitelist_role", "Whitelist Role", "Select the whitelist role for new members"),
        ("nm_status", "View Status", "View new members system status"),
    ],
    "trackers": [
        ("tag_tracker", "Tag Tracker", "Configure server tag tracking and role assignment"),
        ("boost_tracker", "Boost Tracker", "Configure boost log channel"),
        ("tracker_status", "View Status", "View tracker configuration summary"),
    ],
    "updates_drops": [
        ("drops_channel", "Drops Channel", "Set the channel for daily Prime Gaming drops"),
        ("drops_tracker", "Tracked Channels", "Configure which channels to track for stats"),
        ("drops_status", "View Status", "View drops configuration and stats"),
    ],
    "announcements": [
        ("ann_channel", "Announcement Channel", "Set the announcement channel"),
        ("ann_settings", "Thread Settings", "Configure auto-thread behavior"),
        ("ann_status", "View Status", "View announcement configuration summary"),
    ],
    "suggestions": [
        ("sug_channel", "Suggestion Channel", "Set the channel for user suggestions"),
        ("sug_status", "View Status", "View suggestion system stats"),
    ],
    "guide_settings": [
        ("guide_channel", "Guide Channel", "Set a specific channel for the guide (optional)"),
        ("guide_upload", "Guide JSON Builder", "Upload a custom guide JSON file"),
        ("guide_enabled", "Guide Enabled", "Enable or disable the guide system"),
        ("guide_status", "View Status", "View guide system configuration"),
    ],
}


def _build_expired_layout() -> discord.ui.LayoutView:
    """Build the session-expired LayoutView (shared by both expiry helpers)."""
    expired = discord.ui.LayoutView()
    expired.add_item(discord.ui.TextDisplay("## Admin Panel — Session Expired"))
    expired.add_item(discord.ui.Separator())
    expired.add_item(discord.ui.TextDisplay(
        "This panel has timed out after 5 minutes of inactivity.\n"
        "Use `/admin panel` to open a new session."
    ))
    return expired


def attach_timeout_expiry(
    view: discord.ui.LayoutView,
    original_interaction: discord.Interaction,
) -> discord.ui.LayoutView:
    """Attach an on_timeout handler that updates the panel with a session-expired notice.

    Args:
        view:                 The LayoutView to patch.
        original_interaction: The original slash-command interaction used to edit the message.

    Returns:
        The same view, with on_timeout replaced.
    """
    async def on_timeout() -> None:
        try:
            await original_interaction.edit_original_response(view=_build_expired_layout())
        except Exception:
            pass

    view.on_timeout = on_timeout
    return view


def attach_timeout_expiry_msg(
    view: discord.ui.LayoutView,
    message,
) -> discord.ui.LayoutView:
    """Attach an on_timeout handler that edits a specific message with an expiry notice.

    Use this for secondary ephemeral messages (followup sends) where you have the
    message object rather than the original interaction.

    Args:
        view:    The LayoutView to patch.
        message: The message to edit on timeout (WebhookMessage or InteractionMessage).

    Returns:
        The same view, with on_timeout replaced.
    """
    async def on_timeout() -> None:
        try:
            await message.edit(view=_build_expired_layout())
        except Exception:
            pass

    view.on_timeout = on_timeout
    return view


def _build_close_button(admin_user: discord.User, unique_id: int) -> discord.ui.ActionRow:
    """Build a Close Panel button in an ActionRow."""
    close_btn = discord.ui.Button(
        label="Close Panel",
        style=discord.ButtonStyle.danger,
        custom_id=f"close_{unique_id}"
    )

    async def close_callback(interaction: discord.Interaction):
        if interaction.user.id != admin_user.id:
            await interaction.response.send_message(
                "Only the admin who opened this panel can close it.",
                ephemeral=True
            )
            return
        closed_layout = discord.ui.LayoutView()
        closed_layout.add_item(discord.ui.TextDisplay("## Panel Closed"))
        closed_layout.add_item(discord.ui.TextDisplay("Use `/admin panel` to open it again."))
        await interaction.response.edit_message(view=closed_layout)

    close_btn.callback = close_callback

    close_row = discord.ui.ActionRow()
    close_row.add_item(close_btn)
    return close_row


def build_main_panel(
    admin_user: discord.User,
    group_callback: Callable[[discord.Interaction, str], Awaitable[None]]
) -> discord.ui.LayoutView:
    """
    Build the main admin control panel with top-level group selection.

    Args:
        admin_user: The admin user who opened the panel
        group_callback: Async callback that receives (interaction, group_key)

    Returns:
        LayoutView for the main panel
    """
    unique_id = create_unique_id()
    layout = discord.ui.LayoutView(timeout=300.0)

    # Header
    layout.add_item(discord.ui.TextDisplay("## Admin Config Panel"))
    layout.add_item(discord.ui.TextDisplay(
        "Configure settings for this server.\n"
        "Select a settings group to view its options.\n\n"
        "*This panel will timeout after 5 minutes of inactivity.*"
    ))
    layout.add_item(discord.ui.Separator())

    # Group select
    group_select = discord.ui.Select(
        placeholder="Select a settings group...",
        custom_id=f"group_select_{unique_id}",
        options=[
            discord.SelectOption(label=label, value=value, description=desc)
            for value, label, desc in PANEL_GROUPS
        ]
    )

    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != admin_user.id:
            await interaction.response.send_message(
                "Only the admin who opened this panel can interact with it.",
                ephemeral=True
            )
            return
        selected = interaction.data["values"][0]
        await group_callback(interaction, selected)

    group_select.callback = select_callback

    select_row = discord.ui.ActionRow()
    select_row.add_item(group_select)
    layout.add_item(select_row)

    # Close button
    layout.add_item(_build_close_button(admin_user, unique_id))

    return layout


def build_subcategory_panel(
    group_key: str,
    group_label: str,
    admin_user: discord.User,
    subcategory_callback: Callable[[discord.Interaction, str], Awaitable[None]],
    back_callback: Callable[[discord.Interaction], Awaitable[None]],
    locked_keys: set | None = None,
) -> discord.ui.LayoutView:
    """
    Build a subcategory selection panel for a specific settings group.

    Args:
        group_key: The group key (e.g. "embed_settings")
        group_label: Display label for the group (e.g. "Embed Settings")
        admin_user: The admin user who opened the panel
        subcategory_callback: Async callback that receives (interaction, subcategory_value)
        back_callback: Async callback to return to the main panel

    Returns:
        LayoutView for the subcategory panel
    """
    unique_id = create_unique_id()
    subcategories = PANEL_SUBCATEGORIES.get(group_key, [])
    layout = discord.ui.LayoutView(timeout=300.0)

    # Header
    layout.add_item(discord.ui.TextDisplay(f"## {group_label}"))
    options_list = " | ".join(label for _, label, _ in subcategories)
    layout.add_item(discord.ui.TextDisplay(
        f"{options_list}\n\n"
        f"Select an option below to configure."
    ))
    layout.add_item(discord.ui.Separator())

    # Subcategory select
    _locked = locked_keys or set()
    sub_select = discord.ui.Select(
        placeholder=f"Select a {group_label.lower()} option...",
        custom_id=f"subcategory_select_{unique_id}",
        options=[
            discord.SelectOption(
                label=f"🔒 {label}" if value in _locked else label,
                value=value,
                description=desc,
            )
            for value, label, desc in subcategories
        ]
    )

    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != admin_user.id:
            await interaction.response.send_message(
                "Only the admin who opened this panel can interact with it.",
                ephemeral=True
            )
            return
        selected = interaction.data["values"][0]
        await subcategory_callback(interaction, selected)

    sub_select.callback = select_callback

    select_row = discord.ui.ActionRow()
    select_row.add_item(sub_select)
    layout.add_item(select_row)

    # Back and Close buttons
    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=f"back_{unique_id}"
    )

    async def back_btn_callback(interaction: discord.Interaction):
        if interaction.user.id != admin_user.id:
            await interaction.response.send_message(
                "Only the admin who opened this panel can interact with it.",
                ephemeral=True
            )
            return
        await back_callback(interaction)

    back_btn.callback = back_btn_callback

    close_btn = discord.ui.Button(
        label="Close Panel",
        style=discord.ButtonStyle.danger,
        custom_id=f"close_{unique_id}"
    )

    async def close_callback(interaction: discord.Interaction):
        if interaction.user.id != admin_user.id:
            await interaction.response.send_message(
                "Only the admin who opened this panel can close it.",
                ephemeral=True
            )
            return
        closed_layout = discord.ui.LayoutView()
        closed_layout.add_item(discord.ui.TextDisplay("## Panel Closed"))
        closed_layout.add_item(discord.ui.TextDisplay("Use `/admin panel` to open it again."))
        await interaction.response.edit_message(view=closed_layout)

    close_btn.callback = close_callback

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)
    btn_row.add_item(close_btn)
    layout.add_item(btn_row)

    return layout
