"""
Tracker Config Views using Discord Components v2.

Panel views for managing Tag Tracker and Boost Tracker configuration.
"""

import datetime
import discord
from typing import Callable, Awaitable, Dict, Any, List

from Features.trackers.boosts.boost_tracker import as_utc, boost_level_label, format_duration

from .base import AdminLayoutBuilder, cid, readonly_container, editable_container

# TextDisplay caps at 4000 characters and the panel header eats some of that, so the
# boosters display stops adding rows once the body reaches this length.
_BOOSTERS_BODY_BUDGET = 3400


# Shown when a server cannot have a tag, or nobody wears it yet (2026-11-20).
NO_TAGS_TEXT = (
    "This server cannot have a server tag yet. Server tags are a boost perk: once "
    "Discord unlocks them for this server, set your tag in Server Settings and then "
    "switch Tag Tracker on here."
)
NO_WEARERS_TEXT = (
    "Nobody in this server is wearing its tag right now, so there is no tag text to "
    "read yet. Tag Tracker works without it: it fills the tag in by itself as soon as "
    "someone wears it."
)


def tag_status_line(available: bool, detected_tag, wearers: int, stored_tag) -> str:
    """The **Server Tag:** line: what the bot can see, never something typed in."""
    if not available:
        return "Not available (server tags are a boost perk this server does not have)"
    if detected_tag:
        people = "1 member" if wearers == 1 else f"{wearers} members"
        return f"`{detected_tag}` (worn by {people})"
    if stored_tag:
        return f"`{stored_tag}` (nobody is wearing it right now)"
    return "Nobody is wearing this server's tag yet"


def build_tag_tracker_settings_view(
    settings: Dict[str, Any],
    guild: discord.Guild,
    available: bool,
    detected_tag,
    wearers: int,
    on_toggle: Callable[[discord.Interaction, bool], Awaitable[None]],
    on_role_select: Callable[[discord.Interaction, int], Awaitable[None]],
    on_refresh_tag: Callable[[discord.Interaction], Awaitable[None]],
    on_cancel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the Tag Tracker settings view.

    The tag is not typed in (changed 2026-11-20): members are matched by this
    server's id, and the tag text shown here is read from members wearing it.
    """
    builder = AdminLayoutBuilder()

    enabled = settings.get("tag_tracker_enabled", False)
    role_id = settings.get("tag_tracker_role_id")
    server_tag = tag_status_line(
        available, detected_tag, wearers, settings.get("tag_tracker_server_tag"),
    )

    # Role display
    if role_id:
        role = guild.get_role(role_id)
        role_display = role.mention if role else f"Not found ({role_id})"
    else:
        role_display = "Not configured"

    builder.add_header("## Tag Tracker Settings")

    intro = (
        "Gives a role to members wearing this server's tag, and takes it back when "
        "they stop. Tags from other servers never count, even with the same letters."
    )
    if not available:
        intro += f"\n\n{NO_TAGS_TEXT}"
    builder.add_item(readonly_container(discord.ui.TextDisplay(intro)))

    toggle_btn = discord.ui.Button(
        label=f"Tag Tracker: {'ON' if enabled else 'OFF'}",
        style=discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger,
        custom_id=cid("editor", "toggle", "tag_tracker"),
        # Switching ON is impossible without server tags; switching OFF always works.
        disabled=not available and not enabled,
    )

    async def toggle_callback(interaction: discord.Interaction):
        await on_toggle(interaction, not enabled)

    toggle_btn.callback = toggle_callback

    detect_btn = discord.ui.Button(
        label="Refresh Tag",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "detect", "tag_tracker_tag"),
        disabled=not available,
    )
    detect_btn.callback = on_refresh_tag

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


# TagTrackerServerTagModal (type the tag in) was removed 2026-11-20 on the owner's
# ruling: the tag is read from members wearing it, never typed.


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


def format_boosters_display(
    guild: discord.Guild,
    settings: Dict[str, Any],
    stored_boosters: List[Dict[str, Any]],
    recent_events: List[Dict[str, Any]],
    now: datetime.datetime = None,
) -> str:
    """Format the read-only "who is boosting" display as markdown.

    This is the admin-panel home of what used to be the ``/boosters`` and
    ``/boosthistory`` commands: who is boosting right now and how long for, plus the
    recent boost starts and stops for the whole server.

    Current boosters come from the live member cache, which is the same source the old
    ``/boosters`` used. A guild whose members are not chunked would read as having none,
    so in that case the tracker's own collection is used instead - it is reconciled
    against Discord on every startup and written on every boost change.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which renders
    the header and Back button around this body.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    count = guild.premium_subscription_count
    enabled = settings.get("boost_enabled", False)
    channel_id = settings.get("boost_log_channel_id")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    # (label, started_at) pairs, longest-boosting first.
    if guild.chunked:
        boosters = [
            (member.mention, as_utc(member.premium_since))
            for member in guild.premium_subscribers
        ]
    else:
        boosters = [
            (doc.get("username") or f"<@{doc.get('user_id')}>", as_utc(doc.get("boost_start")))
            for doc in stored_boosters
        ]
    boosters.sort(key=lambda pair: pair[1] or now)

    body = (
        f"**Server:** {guild.name}\n"
        f"**Boosts:** {count} - {boost_level_label(count)}\n"
        f"**Boost Tracker:** {'Enabled' if enabled else 'Disabled'}, "
        f"logging to {channel_display}\n\n"
        f"**Currently Boosting - {len(boosters)}**\n"
    )

    if not boosters:
        body += "Nobody is boosting this server right now.\n"
    else:
        shown = 0
        for label, started in boosters:
            if started:
                line = (
                    f"\N{BULLET} {label} - {format_duration(now - started)} "
                    f"(since {started.strftime('%Y-%m-%d')})\n"
                )
            else:
                line = f"\N{BULLET} {label} - start date unknown\n"
            if len(body) + len(line) > _BOOSTERS_BODY_BUDGET:
                break
            body += line
            shown += 1
        if shown < len(boosters):
            body += f"\N{HORIZONTAL ELLIPSIS}and {len(boosters) - shown} more.\n"

    body += "\n**Recent Boost Activity**\n"
    if not recent_events:
        body += (
            "No boost events recorded yet. Starts and stops are only logged while "
            "Boost Tracker is on.\n"
        )
        return body

    shown = 0
    for event in recent_events:
        stamp = as_utc(event.get("timestamp"))
        stamp_display = stamp.strftime("%Y-%m-%d %H:%M") if stamp else "?"
        started = event.get("event_type") == "boost_start"
        action = "started boosting" if started else "stopped boosting"
        duration = event.get("duration")
        extra = f" (lasted {duration})" if duration and not started else ""
        name = event.get("username") or f"<@{event.get('user_id')}>"
        line = f"`{stamp_display}` {name} {action}{extra}\n"
        if len(body) + len(line) > _BOOSTERS_BODY_BUDGET:
            break
        body += line
        shown += 1
    if shown < len(recent_events):
        body += f"\N{HORIZONTAL ELLIPSIS}and {len(recent_events) - shown} more.\n"

    return body


def format_tracker_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of both trackers as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which renders
    the header and Back button around this body.
    """
    # Tag tracker info
    tt_enabled = overview.get("tag_tracker_enabled", False)
    tt_role_id = overview.get("tag_tracker_role_id")
    tt_tag = overview.get("tag_tracker_server_tag") or "Not seen yet"

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
        f"- Server Tag: {tt_tag}\n"
        f"**Boost Tracker:**\n"
        f"- Status: {'Enabled' if bt_enabled else 'Disabled'}\n"
        f"- Log Channel: {bt_channel_display}\n"
        f"- Active Boosters: {boost_stats.get('active_boosters', 0)}\n"
        f"- Total Boost Events: {boost_stats.get('total_events', 0)}"
    )
