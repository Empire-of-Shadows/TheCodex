"""
WYR Config Views using Discord Components v2.

Status view for the WYR configuration panel.
All other WYR panels are handled by the generic panel engine (panel_configs.py).
"""

from typing import Callable, Awaitable, Dict, Any, Optional

import discord

from .base import AdminLayoutBuilder, cid, readonly_container, editable_container

# Archive option labels used by the status view
_ARCHIVE_LABELS = {60: "1 Hour", 1440: "1 Day", 4320: "3 Days", 10080: "1 Week"}


# -- Status View ----------------------------------------------------------

def build_wyr_status_view(stats: Dict[str, Any], guild: discord.Guild) -> discord.ui.LayoutView:
    """Build a read-only status overview of WYR configuration."""
    builder = AdminLayoutBuilder()

    channel_id = stats.get("wyr_channel_id")
    ping_role_id = stats.get("wyr_ping_role_id")
    hour = stats.get("hour", 6)
    minute = stats.get("minute", 0)
    tz = stats.get("timezone", "America/Chicago")
    category = stats.get("default_category", "sfw")
    name_fmt = stats.get("thread_name_format", "")
    starter = stats.get("thread_starter_message", "")
    archive = stats.get("thread_auto_archive", 1440)
    cleanup = stats.get("mapping_cleanup_days", 30)

    archive_label = _ARCHIVE_LABELS.get(archive, f"{archive} min")

    if channel_id:
        channel = guild.get_channel(channel_id)
        channel_display = channel.mention if channel else f"Not found ({channel_id})"
    else:
        channel_display = "Not configured"

    if ping_role_id:
        role = guild.get_role(ping_role_id)
        ping_display = role.mention if role else f"Not found ({ping_role_id})"
    else:
        ping_display = "Not configured"

    builder.add_header("## WYR Configuration Status")
    builder.add_item(readonly_container(
        discord.ui.TextDisplay(
            f"**Server:** {guild.name}\n"
            f"**Channel:** {channel_display}\n"
            f"**Ping Role:** {ping_display}\n"
            f"**Post Time:** {hour:02d}:{minute:02d} ({tz})\n"
            f"**Default Category:** {category}\n"
            f"**Thread Name Format:** `{name_fmt}`\n"
            f"**Starter Message:** {starter[:100]}{'...' if len(starter) > 100 else ''}\n"
            f"**Auto-Archive:** {archive_label}\n"
            f"**Mapping Cleanup:** {cleanup} days"
        ),
    ))

    return builder.build()


# -- Ping Role View -------------------------------------------------------

class WyrCreateRoleModal(discord.ui.Modal):
    """Modal for creating a new Discord role to use as the WYR ping role."""

    def __init__(self, *, on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]]):
        super().__init__(title="Create WYR Ping Role")
        self._callback = on_submit_callback
        self.role_name = discord.ui.TextInput(
            label="Role Name",
            placeholder="e.g., WYR Ping",
            min_length=1,
            max_length=100,
            required=True,
        )
        self.add_item(self.role_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, self.role_name.value.strip())


def build_wyr_ping_role_view(
    current_values: list,
    guild: discord.Guild,
    on_save: Callable[[discord.Interaction, list], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    on_clear: Optional[Callable[[discord.Interaction], Awaitable[None]]],
    on_create_role: Callable[[discord.Interaction], Awaitable[None]],
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """Build the WYR Ping Role select view with an extra Create Role button.

    Mirrors build_select_view for role_select kind but adds a Create Role
    button that opens WyrCreateRoleModal to let admins create a new role
    on the spot and have it auto-selected as the ping role.
    """
    builder = AdminLayoutBuilder()

    builder.add_header("## WYR Ping Role")

    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Role pinged when a WYR question is posted. Leave empty for no ping.\n\n"
        "-# Don't have a dedicated role? Use **Create Role** to create one - "
        "then go to **Server Settings → Roles** to set its color, icon, and position."
    )))

    if current_values:
        mentions = [f"<@&{int(rid)}>" for rid in current_values]
        current_text = f"**Currently assigned:** {', '.join(mentions)}"
    else:
        current_text = "*No role currently assigned.*"

    role_select = discord.ui.RoleSelect(
        placeholder="Select a role...",
        custom_id=cid("editor", "select", "wyr_ping_role"),
        min_values=1,
        max_values=1,
        default_values=[discord.Object(id=int(rid)) for rid in current_values],
    )

    async def _role_cb(interaction: discord.Interaction) -> None:
        role_ids = [int(rid) for rid in interaction.data.get("resolved", {}).get("roles", {}).keys()]
        await on_save(interaction, role_ids)

    role_select.callback = _role_cb

    select_row = discord.ui.ActionRow()
    select_row.add_item(role_select)
    builder.add_item(editable_container(
        discord.ui.TextDisplay(current_text),
        select_row,
    ))

    # Button row: Back/Close | Clear | Create Role
    back_style = discord.ButtonStyle.danger if back_label == "Close" else discord.ButtonStyle.secondary
    back_btn = discord.ui.Button(
        label=back_label,
        style=back_style,
        custom_id=cid("editor", "back", "wyr_ping_role"),
    )
    back_btn.callback = on_back
    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "clear", "wyr_ping_role"),
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        btn_row.add_item(clear_btn)

    create_btn = discord.ui.Button(
        label="Create Role",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "create", "wyr_ping_role"),
    )
    create_btn.callback = on_create_role
    btn_row.add_item(create_btn)

    builder.add_item(btn_row)
    return builder.build()
