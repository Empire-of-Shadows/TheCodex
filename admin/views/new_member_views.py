"""
New Member Config Views using Discord Components v2.

Panel views for managing New Members configuration.
"""

import discord
from typing import Callable, Awaitable, Dict, Any, Optional

from .base import AdminLayoutBuilder, cid, readonly_container, editable_container


def format_new_member_status(overview: Dict[str, Any], guild: discord.Guild) -> str:
    """Format a read-only status overview of New Members configuration as markdown.

    Consumed by the shared ``info_action`` node (see ``panel_configs.py``), which
    renders the header and Back button around this body.
    """
    age = overview.get("account_age_requirement_days", 90)
    auto_kick = overview.get("auto_kick_new_accounts", True)
    greeting_enabled = overview.get("greeting_enabled", True)
    whitelist_enabled = overview.get("whitelist_enabled", True)
    whitelist_role_id = overview.get("whitelist_role_id")
    greeting_channel_id = overview.get("greeting_channel_id")
    stats = overview.get("whitelist_stats", {})

    # Greeting channel display
    if greeting_channel_id:
        greeting_ch = guild.get_channel(greeting_channel_id)
        greeting_display = greeting_ch.mention if greeting_ch else f"Not found ({greeting_channel_id})"
    else:
        greeting_display = "Not configured"

    # Whitelist role display
    if whitelist_role_id:
        role = guild.get_role(whitelist_role_id)
        role_display = role.mention if role else f"Not found ({whitelist_role_id})"
    else:
        role_display = "Not configured"

    return (
        f"**Server:** {guild.name}\n"
        f"**Account Age Requirement:** {age} days\n"
        f"**Auto-Kick New Accounts:** {'Enabled' if auto_kick else 'Disabled'}\n"
        f"**Greeting Messages:** {'Enabled' if greeting_enabled else 'Disabled'}\n"
        f"**Greeting Channel:** {greeting_display}\n"
        f"**Whitelist System:** {'Enabled' if whitelist_enabled else 'Disabled'}\n"
        f"**Whitelist Role:** {role_display}\n\n"
        f"**Whitelist Stats:**\n"
        f"- Active entries: {stats.get('active', 0)}\n"
        f"- Inactive entries: {stats.get('inactive', 0)}\n"
        f"- Total entries: {stats.get('total', 0)}\n"
        f"- Roles currently assigned: {stats.get('role_assigned', 0)}"
    )


# -- Whitelist Role View --------------------------------------------------

class NmCreateRoleModal(discord.ui.Modal):
    """Modal for creating a new Discord role to use as the NM whitelist role."""

    def __init__(self, *, on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]]):
        super().__init__(title="Create Whitelist Role")
        self._callback = on_submit_callback
        self.role_name = discord.ui.TextInput(
            label="Role Name",
            placeholder="e.g., Whitelisted Member",
            min_length=1,
            max_length=100,
            required=True,
        )
        self.add_item(self.role_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, self.role_name.value.strip())


def build_nm_whitelist_role_view(
    current_values: list,
    guild: discord.Guild,
    on_save: Callable[[discord.Interaction, list], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    on_clear: Optional[Callable[[discord.Interaction], Awaitable[None]]],
    on_create_role: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the NM Whitelist Role select view with a Create Role button."""
    builder = AdminLayoutBuilder()

    builder.add_header("## New Members - Whitelist Role")

    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Role assigned to new members added to the whitelist.\n\n"
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
        custom_id=cid("editor", "select", "nm_whitelist_role"),
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

    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back", "nm_whitelist_role"),
    )
    back_btn.callback = on_back
    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "clear", "nm_whitelist_role"),
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        btn_row.add_item(clear_btn)

    create_btn = discord.ui.Button(
        label="Create Role",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "create", "nm_whitelist_role"),
    )
    create_btn.callback = on_create_role
    btn_row.add_item(create_btn)

    builder.add_item(btn_row)
    return builder.build()


# -- Greeting Channel View -------------------------------------------------

class NmCreateChannelModal(discord.ui.Modal):
    """Modal for creating a new text channel to use as the NM greeting channel."""

    def __init__(self, *, on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]]):
        super().__init__(title="Create Greeting Channel")
        self._callback = on_submit_callback
        self.channel_name = discord.ui.TextInput(
            label="Channel Name",
            placeholder="e.g., greeting",
            min_length=1,
            max_length=100,
            required=True,
        )
        self.add_item(self.channel_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction, self.channel_name.value.strip())


def build_nm_greeting_channel_view(
    current_values: list,
    guild: discord.Guild,
    on_save: Callable[[discord.Interaction, list], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    on_clear: Optional[Callable[[discord.Interaction], Awaitable[None]]],
    on_create_channel: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the NM Greeting Channel select view with a Create Channel button."""
    builder = AdminLayoutBuilder()

    builder.add_header("## New Members - Greeting Channel")

    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Channel where greeting messages are sent when new members join.\n\n"
        "-# Don't have a dedicated channel? Use **Create Channel** to create one - "
        "then set its permissions and category in **Server Settings → Channels**."
    )))

    if current_values:
        mentions = [f"<#{int(_cid)}>" for _cid in current_values]
        current_text = f"**Currently assigned:** {', '.join(mentions)}"
    else:
        current_text = "*No channel currently assigned.*"

    channel_select = discord.ui.ChannelSelect(
        placeholder="Select a channel...",
        custom_id=cid("editor", "select", "nm_greeting_channel"),
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1,
        default_values=[discord.Object(id=int(_cid)) for _cid in current_values],
    )

    async def _channel_cb(interaction: discord.Interaction) -> None:
        channel_ids = [
            int(_cid) for _cid in interaction.data.get("resolved", {}).get("channels", {}).keys()
        ]
        await on_save(interaction, channel_ids)

    channel_select.callback = _channel_cb

    select_row = discord.ui.ActionRow()
    select_row.add_item(channel_select)
    builder.add_item(editable_container(
        discord.ui.TextDisplay(current_text),
        select_row,
    ))

    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("editor", "back", "nm_greeting_channel"),
    )
    back_btn.callback = on_back
    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)

    if on_clear is not None:
        clear_btn = discord.ui.Button(
            label="Clear",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "clear", "nm_greeting_channel"),
            disabled=(len(current_values) == 0),
        )
        clear_btn.callback = on_clear
        btn_row.add_item(clear_btn)

    create_btn = discord.ui.Button(
        label="Create Channel",
        style=discord.ButtonStyle.primary,
        custom_id=cid("editor", "create", "nm_greeting_channel"),
    )
    create_btn.callback = on_create_channel
    btn_row.add_item(create_btn)

    builder.add_item(btn_row)
    return builder.build()
