"""Keep a configured channel inside the server it is configured for (2026-11-20).

Several features read a channel id from a server's settings and resolve it with
the global ``bot.get_channel``, which finds a channel in ANY server the bot is in.
A security review found that a settings save could point one server's setting at
another server's channel, and the bot would then post there (WYR, suggestions and
their staff copy, the boost log, drops). The dashboard now refuses such a save;
this is the second lock, at the moment the bot posts, so a stored id from
anywhere (an old document, a future bug) still cannot reach another server.

This module has no ``setup()``, so the cog loader leaves it alone.
"""

from __future__ import annotations

from typing import Optional, TypeVar

from storage.log import get_logger

logger = get_logger("codex.channel_scope")

T = TypeVar("T")


def in_guild(channel: Optional[T], guild_id, *, where: str) -> Optional[T]:
    """``channel`` if it belongs to ``guild_id``, else None (logged).

    A channel with no ``guild`` (a DM or group channel) never counts."""
    if channel is None:
        return None
    if guild_id is None:
        logger.warning(f"Refused {where}: no server to check channel {getattr(channel, 'id', '?')} against")
        return None
    guild = getattr(channel, "guild", None)
    if guild is None or int(guild.id) != int(guild_id):
        logger.warning(
            f"Refused {where}: channel {getattr(channel, 'id', '?')} is not in guild {guild_id}"
        )
        return None
    return channel
