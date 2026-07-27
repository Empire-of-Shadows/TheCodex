"""
Info Board Action Registry & Dispatcher

Named action system for info board component interactions.

All custom_ids use the "b:" prefix. The guide uses "g:", the greeting uses "gr:",
and WYR uses "wyr:" - every decoder matches its prefix WITH the colon, so none of
them collide.

Unlike the greeting's fixed VALID_ACTIONS registry, a board button's main action
points at a *response the admin authored themselves*: a named Components v2 layout
stored alongside the board. That is the whole point of the feature - the extra
information a click reveals is content, not code.

Encodings:
    b:r:<response_id>   send the named response, privately
    b:channel:<id>      point the clicker at a channel
    b:role:<id>         toggle a self-assignable role on the clicker
    b:_select           the board's dropdown; the action rides in the option value

Link buttons carry a URL instead of a custom_id and never reach this module.
"""

from typing import Optional, Tuple

import discord

from storage.log import get_logger

logger = get_logger("BoardActions")

_PREFIX = "b"

# Board actions that a button or a select option can carry. Kept as a set (not a
# handler-bearing registry like the greeting's) because each one's behaviour is
# parameterised by the target, not by a distinct hardcoded handler.
VALID_ACTIONS = {"reply", "channel", "role"}

CUSTOM_ID_SELECT = f"{_PREFIX}:_select"


# ─────────────────────────────────────────────────────────────────────────────
# Custom ID Encoding / Decoding
# ─────────────────────────────────────────────────────────────────────────────

def encode_reply(response_id: str) -> str:
    """Encode a private-reply action: ``b:r:<response_id>``."""
    return f"{_PREFIX}:r:{response_id}"


def encode_channel(channel_id: str) -> str:
    """Encode a channel-pointer action: ``b:channel:<channel_id>``."""
    return f"{_PREFIX}:channel:{channel_id}"


def encode_role(role_id: str) -> str:
    """Encode a role-toggle action: ``b:role:<role_id>``."""
    return f"{_PREFIX}:role:{role_id}"


def encode_custom_id(action: str, target: str) -> str:
    """Encode any board action + target into a custom_id.

    Used by both the renderer and the schema validator, so the validator measures
    exactly the string Discord will receive.
    """
    if action == "reply":
        return encode_reply(target)
    if action == "channel":
        return encode_channel(target)
    if action == "role":
        return encode_role(target)
    return f"{_PREFIX}:{action}:{target}"


def decode_custom_id(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Decode a custom_id into (action, target).

    Returns:
        ("reply", response_id)   for b:r:<response_id>
        ("channel", channel_id)  for b:channel:<channel_id>
        ("role", role_id)        for b:role:<role_id>
        ("_select", None)        for b:_select
        (None, None)             if this is not a board custom_id
    """
    if not raw.startswith(f"{_PREFIX}:"):
        return None, None
    rest = raw[len(_PREFIX) + 1:]

    if rest.startswith("r:"):
        return "reply", rest[2:]
    if rest.startswith("channel:"):
        return "channel", rest[8:]
    if rest.startswith("role:"):
        return "role", rest[5:]
    if rest == "_select":
        return "_select", None

    return None, None


def encode_select_value(action: str, target: str) -> str:
    """Encode a select option value as ``<action>:<target>``."""
    return f"{action}:{target}"


def decode_select_value(value: str) -> Tuple[str, str]:
    """Decode a select option value into (action, target).

    Defaults to a reply action when the value carries no action prefix, so a
    bare response id still resolves.
    """
    if ":" in value:
        action, target = value.split(":", 1)
    else:
        action, target = "reply", value
    return action, target


# ─────────────────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_reply(interaction: discord.Interaction, response_id: str) -> None:
    """Send the named response layout, privately, to whoever clicked."""
    from Features.Board.board_renderer import BoardRenderer
    from Features.Board.board_store import board_store

    board_data = await board_store.get_board(interaction.guild.id)
    if not board_data:
        await interaction.response.send_message(
            "This board is no longer set up.", ephemeral=True
        )
        return

    response = board_store.find_response(board_data, response_id)
    if response is None:
        # The board was re-saved without this response while the old message was
        # still on screen. Say so plainly rather than failing silently.
        logger.warning(
            f"Board response '{response_id}' not found for guild {interaction.guild.id}"
        )
        await interaction.response.send_message(
            "That option is no longer available. The board may have been updated - "
            "try again from the latest message.",
            ephemeral=True,
        )
        return

    layout = BoardRenderer.render_response(
        response, board_data, guild=interaction.guild, member=interaction.user
    )
    await interaction.response.send_message(view=layout, ephemeral=True)


async def _handle_channel(interaction: discord.Interaction, channel_id: str) -> None:
    """Point the clicker at a channel."""
    await interaction.response.send_message(
        f"Head over to <#{channel_id}>!", ephemeral=True
    )


async def _handle_role(interaction: discord.Interaction, role_id: str) -> None:
    """Toggle a self-assignable role on the clicker."""
    guild = interaction.guild
    member = interaction.user
    if not guild or not isinstance(member, discord.Member):
        await interaction.response.send_message(
            "This action is only available in a server.", ephemeral=True
        )
        return

    try:
        role = guild.get_role(int(role_id))
    except (TypeError, ValueError):
        role = None
    if not role:
        await interaction.response.send_message(
            "That role no longer exists.", ephemeral=True
        )
        return

    try:
        if role in member.roles:
            await member.remove_roles(role, reason="Info board role toggle")
            await interaction.response.send_message(
                f"Removed **{role.name}** from you.", ephemeral=True
            )
        else:
            await member.add_roles(role, reason="Info board role toggle")
            await interaction.response.send_message(
                f"Gave you **{role.name}**!", ephemeral=True
            )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to manage that role.", ephemeral=True
        )
    except discord.HTTPException as e:
        logger.error(f"Board role toggle error: {e}", exc_info=True)
        await interaction.response.send_message(
            "Something went wrong managing the role.", ephemeral=True
        )


_HANDLERS = {
    "reply": _handle_reply,
    "channel": _handle_channel,
    "role": _handle_role,
}


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def dispatch_board_interaction(interaction: discord.Interaction) -> bool:
    """Route a board component interaction to its handler.

    Returns True if handled, False if the custom_id isn't ours.

    A posted board outlives every restart, so routing deliberately happens here -
    by custom_id prefix on the raw interaction - rather than through a registered
    persistent View. Nothing needs re-registering when the bot comes back up.
    """
    if interaction.type != discord.InteractionType.component:
        return False

    raw_id = interaction.data.get("custom_id", "")
    action, target = decode_custom_id(raw_id)
    if action is None:
        return False

    # The dropdown carries its action in the chosen value, not the custom_id.
    if action == "_select":
        values = interaction.data.get("values", [])
        if not values:
            return False
        action, target = decode_select_value(values[0])

    handler = _HANDLERS.get(action)
    if handler is None:
        logger.warning(f"Board action '{action}' has no handler")
        return False

    try:
        await handler(interaction, target)
    except Exception as e:
        logger.error(f"Error handling board action '{action}': {e}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong. Please try again.", ephemeral=True
            )

    return True
