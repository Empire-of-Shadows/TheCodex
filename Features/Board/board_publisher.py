"""
Board Publisher

The one place that knows how to get a board onto Discord and keep it there.

A board is a STATIC message: it is posted once and then edited in place, so the
channel never accumulates duplicates. That invariant is enforced here rather than
at each call site, because three surfaces publish boards - `/board post`,
`/board refresh`, and the admin panel's Post action - and they must all behave
identically.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

import discord

from Features.Board.board_renderer import BoardRenderer
from Features.Board.board_schema import validate_board_schema
from Features.Board.board_store import board_store
from storage.log import get_logger

logger = get_logger("BoardPublisher")

Postable = Union[discord.TextChannel, discord.Thread]


@dataclass
class PublishResult:
    """Outcome of a publish attempt. `ok` False always carries a human-readable `error`."""
    ok: bool
    action: str = ""                                # "updated" | "posted" | "reposted"
    message: Optional[discord.Message] = None
    channel: Optional[Postable] = None
    error: Optional[str] = None

    @property
    def summary(self) -> str:
        """A short sentence describing what happened, for a success notice."""
        if not self.ok:
            return self.error or "Something went wrong."
        where = self.channel.mention if self.channel else "the channel"
        if self.action == "updated":
            return f"The board in {where} now shows your latest layout."
        if self.action == "reposted":
            return f"The old board message was gone, so a fresh one was posted in {where}."
        return f"The info board is live in {where}."


async def fetch_posted_message(
    guild: discord.Guild, doc: Optional[Dict[str, Any]]
) -> Optional[discord.Message]:
    """Fetch the board message this guild currently has posted, or None.

    Every failure path returns None on purpose: a board whose message was deleted
    (or whose channel was removed) must not block a re-post.
    """
    if not doc:
        return None

    channel_id = doc.get("channel_id")
    message_id = doc.get("message_id")
    if not channel_id or not message_id:
        return None

    try:
        channel = guild.get_channel(int(channel_id))
    except (TypeError, ValueError):
        return None
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return None

    try:
        return await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden):
        return None
    except (discord.HTTPException, TypeError, ValueError) as e:
        logger.warning(f"Could not fetch board message for guild {guild.id}: {e}")
        return None


async def load_valid_board(guild_id: int) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load a guild's board and validate it.

    Returns (board_data, None) or (None, error). Validating on the way out means a
    layout that was hand-edited into an invalid state can never be pushed live.
    """
    board_data = await board_store.get_board(guild_id)
    if not board_data:
        return None, (
            "This server has no info board yet.\n\n"
            "**Set it up:** `/admin panel` -> **Info Board -> Board Builder** and "
            "upload a JSON layout, or build one in the dashboard."
        )

    valid, msg = validate_board_schema(board_data)
    if not valid:
        return None, f"The saved board layout is invalid: {msg}"

    return board_data, None


async def publish(
    guild: discord.Guild,
    channel: Optional[Postable] = None,
) -> PublishResult:
    """Publish the guild's board, editing the existing message where possible.

    channel:
        None  - refresh wherever the board already lives (or repost there if the
                message was deleted).
        given - post there; if the board was live somewhere else, the old copy is
                removed so only one board exists per guild.
    """
    board_data, error = await load_valid_board(guild.id)
    if board_data is None:
        return PublishResult(ok=False, error=error)

    doc = await board_store.get_document(guild.id)
    existing = await fetch_posted_message(guild, doc)

    target, error = _resolve_target(guild, doc, existing, channel)
    if target is None:
        return PublishResult(ok=False, error=error)

    layout = BoardRenderer.render_board(board_data, guild=guild)

    try:
        if existing is not None and existing.channel.id == target.id:
            await existing.edit(view=layout)
            message, action = existing, "updated"
        else:
            message = await target.send(view=layout)
            action = "posted" if existing is not None else (
                "reposted" if (doc or {}).get("message_id") else "posted"
            )
            if existing is not None:
                # Relocating: drop the old copy so one board stays one board.
                try:
                    await existing.delete()
                except discord.HTTPException:
                    logger.warning(
                        f"Could not remove the previous board message for guild "
                        f"{guild.id}; it may need deleting by hand."
                    )
    except discord.Forbidden:
        return PublishResult(
            ok=False, error=f"I don't have permission to post in {target.mention}."
        )
    except discord.HTTPException as e:
        logger.error(f"Failed to publish board for guild {guild.id}: {e}", exc_info=True)
        return PublishResult(ok=False, error=f"Discord rejected the board message: {e}")

    await board_store.set_posted_message(guild.id, target.id, message.id)
    logger.info(
        f"Board {action} in guild {guild.id} channel {target.id} (message {message.id})"
    )
    return PublishResult(ok=True, action=action, message=message, channel=target)


def _resolve_target(
    guild: discord.Guild,
    doc: Optional[Dict[str, Any]],
    existing: Optional[discord.Message],
    channel: Optional[Postable],
) -> tuple[Optional[Postable], Optional[str]]:
    """Work out which channel to publish into."""
    if channel is not None:
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None, "The board can only be posted in a text channel or thread."
        return channel, None

    if existing is not None:
        return existing.channel, None

    # No live message. Fall back to the channel it used to live in.
    channel_id = (doc or {}).get("channel_id")
    if channel_id:
        try:
            stored = guild.get_channel(int(channel_id))
        except (TypeError, ValueError):
            stored = None
        if isinstance(stored, (discord.TextChannel, discord.Thread)):
            return stored, None

    return None, "There's no board posted yet. Use `/board post #channel` to put one up."
