"""
Drops Config Views using Discord Components v2.

Panel views for managing the Updates & Drops system configuration:
- Drops posting channel
- Tracked channels (Updates / Free / Prime)
- Read-only status with stats
"""

import discord
from typing import Callable, Awaitable, Dict, Any

from .base import create_unique_id, AdminLayoutBuilder


TRACKER_CATEGORIES = ("Updates", "Free", "Prime")


def build_drops_channel_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    on_channel_select: Callable[[discord.Interaction, int], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
    on_toggle: Callable[[discord.Interaction], Awaitable[None]] | None = None,
) -> discord.ui.LayoutView:
    """Build the Drops posting channel configuration view."""
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    channel_id = settings.get("drops_channel_id")
    enabled = settings.get("drops_enabled", False)

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    status_display = "✅ Enabled" if enabled else "❌ Disabled"

    builder.add_header("## Drops Channel")
    builder.add_text(
        f"**Current Channel:** {channel_display}\n"
        f"**Status:** {status_display}\n\n"
        "Select a channel below for daily Prime Gaming drops posts."
    )
    builder.add_separator()

    # Channel select
    channel_select = discord.ui.ChannelSelect(
        placeholder="Select drops posting channel...",
        custom_id=f"drops_ch_{unique_id}",
        channel_types=[discord.ChannelType.text],
    )

    async def channel_callback(interaction: discord.Interaction):
        selected_channel = interaction.data["values"][0]
        await on_channel_select(interaction, int(selected_channel))

    channel_select.callback = channel_callback

    select_row = discord.ui.ActionRow()
    select_row.add_item(channel_select)
    builder.add_item(select_row)

    # Toggle + Done buttons
    btn_row = discord.ui.ActionRow()

    if channel_id and on_toggle is not None:
        toggle_btn = discord.ui.Button(
            label="Disable" if enabled else "Enable",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            custom_id=f"drops_ch_toggle_{unique_id}",
        )
        toggle_btn.callback = on_toggle
        btn_row.add_item(toggle_btn)

    done_btn = discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.secondary,
        custom_id=f"drops_ch_done_{unique_id}",
    )
    done_btn.callback = on_cancel
    btn_row.add_item(done_btn)

    builder.add_item(btn_row)

    return builder.build()


def build_drops_tracker_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    on_channel_select: Callable[[discord.Interaction, str, int], Awaitable[None]],
    on_remove: Callable[[discord.Interaction, str], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the tracked channels configuration view (Updates/Free/Prime)."""
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    tracker_channels = settings.get("drops_tracker_channels", {})

    # Build status text
    lines = []
    for category in TRACKER_CATEGORIES:
        ch_id = tracker_channels.get(category)
        if ch_id:
            ch = guild.get_channel(ch_id)
            display = ch.mention if ch else f"Not found ({ch_id})"
        else:
            display = "Not configured"
        lines.append(f"- **{category}:** {display}")

    builder.add_header("## Tracked Channels")
    builder.add_text(
        "Configure which channels to track for drops statistics.\n\n"
        + "\n".join(lines)
    )
    builder.add_separator()

    # Per-category channel selects
    for category in TRACKER_CATEGORIES:
        ch_select = discord.ui.ChannelSelect(
            placeholder=f"Set channel for {category}...",
            custom_id=f"drops_trk_{category}_{unique_id}",
            channel_types=[discord.ChannelType.text],
        )

        def _make_ch_callback(cat: str):
            async def ch_callback(interaction: discord.Interaction):
                selected_ch = interaction.data["values"][0]
                await on_channel_select(interaction, cat, int(selected_ch))
            return ch_callback

        ch_select.callback = _make_ch_callback(category)

        ch_row = discord.ui.ActionRow()
        ch_row.add_item(ch_select)
        builder.add_item(ch_row)

    # Done button
    done_btn = discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.secondary,
        custom_id=f"drops_trk_done_{unique_id}",
    )
    done_btn.callback = on_cancel

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(done_btn)
    builder.add_item(btn_row)

    return builder.build()


def build_drops_status_view(
    overview: Dict[str, Any],
    guild: discord.Guild,
) -> discord.ui.LayoutView:
    """Build a read-only status overview of drops configuration and stats."""
    builder = AdminLayoutBuilder()

    # Drops channel
    drops_ch_id = overview.get("drops_channel_id")
    if drops_ch_id:
        ch = guild.get_channel(drops_ch_id)
        drops_display = ch.mention if ch else f"Not found ({drops_ch_id})"
    else:
        drops_display = "Not configured"

    enabled_display = "✅ Enabled" if overview.get("drops_enabled", False) else "❌ Disabled"

    # Tracked channels
    tracker_channels = overview.get("drops_tracker_channels", {})
    tracker_lines = []
    for category in TRACKER_CATEGORIES:
        ch_id = tracker_channels.get(category)
        if ch_id:
            ch = guild.get_channel(ch_id)
            display = ch.mention if ch else f"Not found ({ch_id})"
        else:
            display = "Not configured"
        tracker_lines.append(f"- **{category}:** {display}")

    # Stats
    stats = overview.get("stats", {})
    stats_lines = []
    for category in TRACKER_CATEGORIES:
        cat_stats = stats.get(category, {})
        total = cat_stats.get("total_count", 0)
        avg = cat_stats.get("average_per_month", 0.0)
        months = cat_stats.get("months_with_data", 0)
        stats_lines.append(f"- **{category}:** {total} total | {avg}/mo avg | {months} months tracked")

    builder.add_header("## Updates & Drops Status")
    builder.add_text(f"**Server:** {guild.name}")
    builder.add_separator()

    builder.add_text(
        f"**Drops Posting Channel:** {drops_display}\n"
        f"**Status:** {enabled_display}"
    )
    builder.add_separator()

    builder.add_text(
        "**Tracked Channels:**\n" + "\n".join(tracker_lines)
    )
    builder.add_separator()

    builder.add_text(
        "**Statistics (Guild):**\n" + "\n".join(stats_lines)
    )

    return builder.build()
