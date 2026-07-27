"""
Shared "not set up yet" notices.

Every feature command that runs into an unconfigured guild routes through here,
so a member always learns the same three things in the same order: what is
missing, that ``/admin panel`` is where it gets fixed, and who can actually fix
it right now.

That last part is the reason this is shared rather than inlined. On a fresh
install no roles are delegated yet, so the only people who can open the panel are
the server owner and anyone with Manage Server. Telling a regular member to "run
/admin panel" would be dead advice. Instead the notice names the owner and points
them at Role Configuration first, so they can hand panel access to their staff and
stop being the only person who can set anything up.

Nothing here pings: the owner is rendered as a plain name, never a mention, because
these notices can fire on any member's command in any channel.
"""

from typing import Optional

import discord

from storage.log import get_logger
from storage.settings.config_manager import get_config

logger = get_logger("SetupNotice")

PANEL_COMMAND = "`/admin panel`"

# Panel breadcrumbs used by more than one caller. Labels mirror the MAIN_PANEL
# tree in admin/settings/panel_configs.py - keep them in step if a label changes.
ROLE_CONFIG_PATH = "Role Configuration -> Panel Access Roles"


def _owner_name(guild: Optional[discord.Guild]) -> str:
    """Owner's display name, as plain text. Falls back when the member is uncached."""
    owner = getattr(guild, "owner", None)
    if owner is not None:
        return f"**{owner.display_name}**"
    return "the server owner"


async def _audience_line(
    guild: Optional[discord.Guild],
    viewer: Optional[discord.Member],
) -> str:
    """The 'who can fix this' sentence, tailored to the guild and the viewer.

    Fails soft: if config cannot be read we assume access has been delegated, which
    yields the neutral "ask an admin" wording rather than wrongly nagging the owner.
    """
    if guild is None:
        return ""

    delegated = True
    viewer_has_access = False
    try:
        config = await get_config(guild.id)
        admin_roles = set(config.roles["admin_role_ids"])
        mod_roles = set(config.roles["mod_role_ids"])
        delegated = bool(admin_roles or mod_roles)

        perms = getattr(viewer, "guild_permissions", None)
        if perms and perms.manage_guild:
            viewer_has_access = True
        elif viewer is not None:
            viewer_role_ids = {role.id for role in getattr(viewer, "roles", [])}
            viewer_has_access = bool(viewer_role_ids & admin_roles)
    except Exception as e:
        logger.warning(f"Could not read roles config for guild {guild.id}: {e}")

    if viewer_has_access:
        line = "You have panel access, so you can set this up yourself."
        if not delegated:
            # The one person who can fix it is reading: also nudge them to share
            # the load, since right now nobody else can configure anything.
            line += (
                f"\nNo one else can yet - add your staff roles under {PANEL_COMMAND} -> "
                f"**{ROLE_CONFIG_PATH}** so they can help."
            )
        return line

    if not delegated:
        return (
            f"Only {_owner_name(guild)} and members with **Manage Server** can open the "
            f"panel right now.\n"
            f"{_owner_name(guild)}: add your staff roles under {PANEL_COMMAND} -> "
            f"**{ROLE_CONFIG_PATH}** so they can help set the server up."
        )

    return f"Ask an admin or moderator to run {PANEL_COMMAND}."


async def setup_notice_text(
    guild: Optional[discord.Guild],
    *,
    what: str,
    path: str,
    viewer: Optional[discord.Member] = None,
    detail: str = "",
) -> str:
    """Build the plain-text form of a setup notice.

    Args:
        guild:  The guild the notice is about.
        what:   What is missing, as a noun phrase - "Would You Rather notifications",
                "a suggestion channel". Phrased into the opening sentence, so it
                reads naturally whether it is singular or plural.
        path:   Breadcrumb inside the admin panel, e.g. "WYR Settings -> WYR Channel".
        viewer: The member who will read this, so the notice can address them
                directly when they already have panel access.
        detail: Optional extra sentence appended after the opening line.
    """
    parts = [f"This server has not set up **{what}** yet."]
    if detail:
        parts.append(detail)
    parts.append(f"**Set it up:** {PANEL_COMMAND} -> **{path}**")

    audience = await _audience_line(guild, viewer)
    if audience:
        parts.append(audience)

    return "\n\n".join(parts)


async def setup_notice_embed(
    guild: Optional[discord.Guild],
    *,
    what: str,
    path: str,
    viewer: Optional[discord.Member] = None,
    detail: str = "",
    title: str = "Not Set Up Yet",
) -> discord.Embed:
    """The embed form of the same notice."""
    description = await setup_notice_text(
        guild, what=what, path=path, viewer=viewer, detail=detail
    )
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.orange(),
    )


async def send_setup_notice(
    interaction: discord.Interaction,
    *,
    what: str,
    path: str,
    detail: str = "",
    title: str = "Not Set Up Yet",
) -> None:
    """Send a setup notice ephemerally, respecting whether the interaction was answered."""
    embed = await setup_notice_embed(
        interaction.guild,
        what=what,
        path=path,
        viewer=interaction.user if isinstance(interaction.user, discord.Member) else None,
        detail=detail,
        title=title,
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException as e:
        logger.debug(f"Could not deliver setup notice: {e}")


async def permission_notice_embed(
    guild: Optional[discord.Guild],
    *,
    action: str,
    admin_only: bool = False,
) -> discord.Embed:
    """Notice for a staff-only command run by someone without the tier.

    Beyond "you can't", this explains how the tier is granted, since on a fresh
    install the answer is "nobody has delegated it yet" rather than "you were
    denied".
    """
    tier = "the configured **Panel Access** role" if admin_only else (
        "a configured **Panel Access** or **Mod Access** role"
    )
    parts = [
        f"You need **Administrator** or {tier} to {action}.",
    ]

    delegated = True
    try:
        if guild is not None:
            config = await get_config(guild.id)
            delegated = bool(
                config.roles["admin_role_ids"] or config.roles["mod_role_ids"]
            )
    except Exception as e:
        logger.warning(f"Could not read roles config for guild {getattr(guild, 'id', '?')}: {e}")

    if not delegated:
        parts.append(
            f"No staff roles have been set up yet, so only {_owner_name(guild)} and "
            f"members with **Manage Server** can use this.\n"
            f"{_owner_name(guild)}: assign them under {PANEL_COMMAND} -> "
            f"**{ROLE_CONFIG_PATH}**."
        )

    return discord.Embed(
        title="Permission Denied",
        description="\n\n".join(parts),
        color=discord.Color.red(),
    )
