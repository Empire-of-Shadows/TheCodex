"""
Tracker Config Views using Discord Components v2.

Panel views for managing Tag Tracker and Boost Tracker configuration.
"""

import discord
from typing import Callable, Awaitable, Dict, Any

from .base import AdminLayoutBuilder, cid, readonly_container, editable_container


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

    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Track members holding a specific server tag and assign them a role."
    )))

    toggle_btn = discord.ui.Button(
        label=f"Tag Tracker: {'ON' if enabled else 'OFF'}",
        style=discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger,
        custom_id=cid("editor", "toggle", "tag_tracker"),
    )

    async def toggle_callback(interaction: discord.Interaction):
        await on_toggle(interaction, not enabled)

    toggle_btn.callback = toggle_callback

    tag_btn = discord.ui.Button(
        label="Edit Server Tag",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "edit", "tag_tracker_tag"),
    )
    tag_btn.callback = on_edit_tag

    detect_btn = discord.ui.Button(
        label="Detect Tag",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "detect", "tag_tracker_tag"),
    )
    detect_btn.callback = on_detect_tag

    role_select = discord.ui.RoleSelect(
        placeholder="Select role to assign for server tag...",
        custom_id=cid("editor", "select", "tag_tracker_role"),
        default_values=(
            [discord.Object(id=int(role_id))] if role_id else []
        ),
    )

    async def role_callback(interaction: discord.Interaction):
        selected_role = interaction.data["values"][0]
        await on_role_select(interaction, int(selected_role))

    role_select.callback = role_callback

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(toggle_btn)
    btn_row.add_item(tag_btn)
    btn_row.add_item(detect_btn)

    select_row = discord.ui.ActionRow()
    select_row.add_item(role_select)

    builder.add_item(editable_container(
        discord.ui.TextDisplay(
            f"**Status:** {'Enabled' if enabled else 'Disabled'}\n"
            f"**Tracked Role:** {role_display}\n"
            f"**Server Tag:** {server_tag}"
        ),
        btn_row,
        select_row,
    ))

    done_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back", "tag_tracker"),
    )
    done_btn.callback = on_cancel

    done_row = discord.ui.ActionRow()
    done_row.add_item(done_btn)
    builder.add_item(done_row)

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
    builder = AdminLayoutBuilder()

    enabled = settings.get("boost_enabled", False)
    channel_id = settings.get("boost_log_channel_id")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    builder.add_header("## Boost Tracker Settings")
    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Select a channel below to log boost events."
    )))

    toggle_btn = discord.ui.Button(
        label=f"Boost Tracker: {'ON' if enabled else 'OFF'}",
        style=discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger,
        custom_id=cid("editor", "toggle", "boost_tracker"),
    )

    async def toggle_callback(interaction: discord.Interaction):
        await on_toggle(interaction, not enabled)

    toggle_btn.callback = toggle_callback

    channel_select = discord.ui.ChannelSelect(
        placeholder="Select boost log channel...",
        custom_id=cid("editor", "select", "boost_tracker_channel"),
        channel_types=[discord.ChannelType.text],
        default_values=(
            [discord.Object(id=int(channel_id))] if channel_id else []
        ),
    )

    async def channel_callback(interaction: discord.Interaction):
        selected_channel = interaction.data["values"][0]
        await on_channel_select(interaction, int(selected_channel))

    channel_select.callback = channel_callback

    toggle_row = discord.ui.ActionRow()
    toggle_row.add_item(toggle_btn)

    select_row = discord.ui.ActionRow()
    select_row.add_item(channel_select)

    builder.add_item(editable_container(
        discord.ui.TextDisplay(
            f"**Status:** {'Enabled' if enabled else 'Disabled'}\n"
            f"**Boost Log Channel:** {channel_display}"
        ),
        toggle_row,
        select_row,
    ))

    done_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back", "boost_tracker"),
    )
    done_btn.callback = on_cancel

    done_row = discord.ui.ActionRow()
    done_row.add_item(done_btn)
    builder.add_item(done_row)

    return builder.build()


def format_tracker_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of both trackers as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which renders
    the header and Back button around this body.
    """
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

    return (
        f"**Server:** {guild.name}\n\n"
        f"**Tag Tracker:**\n"
        f"- Status: {'Enabled' if tt_enabled else 'Disabled'}\n"
        f"- Tracked Role: {tt_role_display}\n"
        f"- Server Tag: {tt_tag}\n\n"
        f"**Boost Tracker:**\n"
        f"- Status: {'Enabled' if bt_enabled else 'Disabled'}\n"
        f"- Log Channel: {bt_channel_display}\n"
        f"- Active Boosters: {boost_stats.get('active_boosters', 0)}\n"
        f"- Total Boost Events: {boost_stats.get('total_events', 0)}"
    )
