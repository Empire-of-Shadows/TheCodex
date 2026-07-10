"""
Drops Config Views using Discord Components v2.

Panel views for managing the Updates & Drops system configuration:
- Drops posting channel
- Tracked channels (Updates / Free / Prime)
- Read-only status with stats
"""

import discord
from typing import Callable, Awaitable, Dict, Any

from .base import AdminLayoutBuilder, cid, readonly_container, editable_container


TRACKER_CATEGORIES = ("Updates", "Free", "Prime")


def build_drops_channel_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    on_channel_select: Callable[[discord.Interaction, int], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
    on_toggle: Callable[[discord.Interaction], Awaitable[None]] | None = None,
) -> discord.ui.LayoutView:
    """Build the Drops posting channel configuration view."""
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
    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Select a channel below for daily Prime Gaming drops posts."
    )))

    channel_select = discord.ui.ChannelSelect(
        placeholder="Select drops posting channel...",
        custom_id=cid("editor", "select", "drops_channel"),
        channel_types=[discord.ChannelType.text],
        default_values=(
            [discord.Object(id=int(channel_id))] if channel_id else []
        ),
    )

    async def channel_callback(interaction: discord.Interaction):
        selected_channel = interaction.data["values"][0]
        await on_channel_select(interaction, int(selected_channel))

    channel_select.callback = channel_callback

    select_row = discord.ui.ActionRow()
    select_row.add_item(channel_select)

    btn_row = discord.ui.ActionRow()

    if channel_id and on_toggle is not None:
        toggle_btn = discord.ui.Button(
            label="Disable" if enabled else "Enable",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            custom_id=cid("editor", "toggle", "drops_channel"),
        )
        toggle_btn.callback = on_toggle
        btn_row.add_item(toggle_btn)

    builder.add_item(editable_container(
        discord.ui.TextDisplay(
            f"**Current Channel:** {channel_display}\n"
            f"**Status:** {status_display}"
        ),
        select_row,
        btn_row,
    ))

    done_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back", "drops_channel"),
    )
    done_btn.callback = on_cancel

    done_row = discord.ui.ActionRow()
    done_row.add_item(done_btn)
    builder.add_item(done_row)

    return builder.build()


def build_drops_tracker_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    on_channel_select: Callable[[discord.Interaction, str, int], Awaitable[None]],
    on_remove: Callable[[discord.Interaction, str], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the tracked channels configuration view (Updates/Free/Prime)."""
    builder = AdminLayoutBuilder()

    tracker_channels = settings.get("drops_tracker_channels", {})

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
    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Configure which channels to track for drops statistics."
    )))

    editor_items: list[discord.ui.Item] = [discord.ui.TextDisplay("\n".join(lines))]
    for category in TRACKER_CATEGORIES:
        cat_ch_id = tracker_channels.get(category)
        ch_select = discord.ui.ChannelSelect(
            placeholder=f"Set channel for {category}...",
            custom_id=cid("editor", "select", f"drops_tracker_{category.lower()}"),
            channel_types=[discord.ChannelType.text],
            default_values=(
                [discord.Object(id=int(cat_ch_id))] if cat_ch_id else []
            ),
        )

        def _make_ch_callback(cat: str):
            async def ch_callback(interaction: discord.Interaction):
                selected_ch = interaction.data["values"][0]
                await on_channel_select(interaction, cat, int(selected_ch))
            return ch_callback

        ch_select.callback = _make_ch_callback(category)
        ch_row = discord.ui.ActionRow()
        ch_row.add_item(ch_select)
        editor_items.append(ch_row)

    builder.add_item(editable_container(*editor_items))

    done_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back", "drops_tracker"),
    )
    done_btn.callback = on_cancel

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(done_btn)
    builder.add_item(btn_row)

    return builder.build()


def format_drops_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of drops configuration and stats as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which
    renders the header and Back button around this body.
    """
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

    schedule = overview.get("schedule", {}) or {}
    sched_hour = schedule.get("hour", 6)
    sched_min = schedule.get("minute", 30)
    sched_tz = schedule.get("timezone", "America/Chicago")
    schedule_display = f"{sched_hour:02d}:{sched_min:02d} {sched_tz}"

    return (
        f"**Server:** {guild.name}\n"
        f"**Drops Posting Channel:** {drops_display}\n"
        f"**Status:** {enabled_display}\n"
        f"**Daily Post Time:** {schedule_display}\n\n"
        "**Tracked Channels:**\n" + "\n".join(tracker_lines) + "\n\n"
        "**Statistics (Guild):**\n" + "\n".join(stats_lines)
    )
