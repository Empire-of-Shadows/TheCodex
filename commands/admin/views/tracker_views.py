"""
Tracker Config Views using Discord Components v2.

Panel views for managing Tag Tracker and Boost Tracker configuration.
"""

import discord
from typing import Callable, Awaitable, Dict, Any

from .base import create_unique_id, AdminLayoutBuilder


def build_tag_tracker_settings_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    on_toggle: Callable[[discord.Interaction, bool], Awaitable[None]],
    on_role_select: Callable[[discord.Interaction, int], Awaitable[None]],
    on_edit_tag: Callable[[discord.Interaction], Awaitable[None]],
    on_detect_tag: Callable[[discord.Interaction], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the Tag Tracker settings view."""
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    enabled = settings.get("tag_tracker_enabled", False)
    role_id = settings.get("tag_tracker_role_id")
    server_tag = settings.get("tag_tracker_server_tag") or "Not set"

    # Role display
    if role_id:
        role = guild.get_role(role_id)
        role_display = role.mention if role else f"Not found ({role_id})"
    else:
        role_display = "Not configured"

    builder.add_header("## Tag Tracker Settings")
    builder.add_text(
        f"**Status:** {'Enabled' if enabled else 'Disabled'}\n"
        f"**Tracked Role:** {role_display}\n"
        f"**Server Tag:** {server_tag}"
    )
    builder.add_separator()

    # Toggle button
    toggle_btn = discord.ui.Button(
        label=f"Tag Tracker: {'ON' if enabled else 'OFF'}",
        style=discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger,
        custom_id=f"tt_toggle_{unique_id}",
    )

    async def toggle_callback(interaction: discord.Interaction):
        await on_toggle(interaction, not enabled)

    toggle_btn.callback = toggle_callback

    # Edit tag button
    tag_btn = discord.ui.Button(
        label="Edit Server Tag",
        style=discord.ButtonStyle.primary,
        custom_id=f"tt_tag_{unique_id}",
    )
    tag_btn.callback = on_edit_tag

    # Detect tag button
    detect_btn = discord.ui.Button(
        label="Detect Tag",
        style=discord.ButtonStyle.primary,
        custom_id=f"tt_detect_{unique_id}",
    )
    detect_btn.callback = on_detect_tag

    # Done button
    done_btn = discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.secondary,
        custom_id=f"tt_done_{unique_id}",
    )
    done_btn.callback = on_cancel

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(toggle_btn)
    btn_row.add_item(tag_btn)
    btn_row.add_item(detect_btn)
    btn_row.add_item(done_btn)
    builder.add_item(btn_row)

    # Role select dropdown
    role_select = discord.ui.RoleSelect(
        placeholder="Select role to assign for server tag...",
        custom_id=f"tt_role_{unique_id}",
    )

    async def role_callback(interaction: discord.Interaction):
        selected_role = interaction.data["values"][0]
        await on_role_select(interaction, int(selected_role))

    role_select.callback = role_callback

    select_row = discord.ui.ActionRow()
    select_row.add_item(role_select)
    builder.add_item(select_row)

    return builder.build()


class TagTrackerServerTagModal(discord.ui.Modal, title="Server Tag"):
    """Modal for entering the Discord server tag string."""

    tag_input = discord.ui.TextInput(
        label="Server Tag",
        placeholder="e.g., EoS",
        required=True,
        min_length=1,
        max_length=32,
    )

    def __init__(self, callback: Callable, current_tag: str = ""):
        super().__init__()
        self._callback = callback
        self.tag_input.default = current_tag

    async def on_submit(self, interaction: discord.Interaction):
        tag = self.tag_input.value.strip()
        await self._callback(interaction, tag)


def build_boost_tracker_settings_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    on_toggle: Callable[[discord.Interaction, bool], Awaitable[None]],
    on_channel_select: Callable[[discord.Interaction, int], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the Boost Tracker settings view."""
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    enabled = settings.get("boost_enabled", False)
    channel_id = settings.get("boost_log_channel_id")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    builder.add_header("## Boost Tracker Settings")
    builder.add_text(
        f"**Status:** {'Enabled' if enabled else 'Disabled'}\n"
        f"**Boost Log Channel:** {channel_display}\n\n"
        "Select a channel below to log boost events."
    )
    builder.add_separator()

    # Toggle button
    toggle_btn = discord.ui.Button(
        label=f"Boost Tracker: {'ON' if enabled else 'OFF'}",
        style=discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger,
        custom_id=f"bt_toggle_{unique_id}",
    )

    async def toggle_callback(interaction: discord.Interaction):
        await on_toggle(interaction, not enabled)

    toggle_btn.callback = toggle_callback

    # Done button
    done_btn = discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.secondary,
        custom_id=f"bt_done_{unique_id}",
    )
    done_btn.callback = on_cancel

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(toggle_btn)
    btn_row.add_item(done_btn)
    builder.add_item(btn_row)

    # Channel select
    channel_select = discord.ui.ChannelSelect(
        placeholder="Select boost log channel...",
        custom_id=f"bt_channel_{unique_id}",
        channel_types=[discord.ChannelType.text],
    )

    async def channel_callback(interaction: discord.Interaction):
        selected_channel = interaction.data["values"][0]
        await on_channel_select(interaction, int(selected_channel))

    channel_select.callback = channel_callback

    select_row = discord.ui.ActionRow()
    select_row.add_item(channel_select)
    builder.add_item(select_row)

    return builder.build()


def build_tracker_status_view(
    overview: Dict[str, Any],
    guild: discord.Guild,
) -> discord.ui.LayoutView:
    """Build a read-only status overview of both trackers."""
    builder = AdminLayoutBuilder()

    # Tag tracker info
    tt_enabled = overview.get("tag_tracker_enabled", False)
    tt_role_id = overview.get("tag_tracker_role_id")
    tt_tag = overview.get("tag_tracker_server_tag") or "Not set"

    if tt_role_id:
        role = guild.get_role(tt_role_id)
        tt_role_display = role.mention if role else f"Not found ({tt_role_id})"
    else:
        tt_role_display = "Not configured"

    # Boost tracker info
    bt_enabled = overview.get("boost_enabled", False)
    bt_channel_id = overview.get("boost_log_channel_id")
    if bt_channel_id:
        channel = guild.get_channel(bt_channel_id)
        bt_channel_display = channel.mention if channel else f"Not found ({bt_channel_id})"
    else:
        bt_channel_display = "Not configured"

    boost_stats = overview.get("boost_stats", {})

    builder.add_header("## Tracker Status")
    builder.add_text(f"**Server:** {guild.name}")
    builder.add_separator()

    builder.add_text(
        f"**Tag Tracker:**\n"
        f"- Status: {'Enabled' if tt_enabled else 'Disabled'}\n"
        f"- Tracked Role: {tt_role_display}\n"
        f"- Server Tag: {tt_tag}"
    )
    builder.add_separator()

    builder.add_text(
        f"**Boost Tracker:**\n"
        f"- Status: {'Enabled' if bt_enabled else 'Disabled'}\n"
        f"- Log Channel: {bt_channel_display}\n"
        f"- Active Boosters: {boost_stats.get('active_boosters', 0)}\n"
        f"- Total Boost Events: {boost_stats.get('total_events', 0)}"
    )

    return builder.build()
