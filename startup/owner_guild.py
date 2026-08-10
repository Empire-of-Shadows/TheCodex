"""
The guild that owns the bot's private, guild-scoped slash commands.

Owner tooling (`/wyrbank`, `/status`) has no business in the command list of
every server the bot is in. Registering those commands to a single guild keeps
them out of sight; the per-command ownership check is still what actually gates
them, because guild scoping is tidiness rather than security.

One constant, resolved in one place. There used to be two - ``STATUS_ADMIN_GUILD_ID``
for `/status` and ``OWNER_GUILD_ID`` for `/wyrbank` - and only the first was
synced by the entrypoint, so anything using the second was defined for a guild
that was never synced and silently never appeared. ``OWNER_GUILD_ID`` is the
name going forward; the older one is still honoured so an environment that only
sets it keeps working.

Unset (or 0) means no guild sync happens at all and the cogs that depend on it
do not load, which is the safe default for a fresh environment.
"""

from __future__ import annotations

import os


def get_owner_guild_id() -> int:
    """Return the private command guild id, or 0 when none is configured.

    Read at call time rather than import time so a test or a tool can set the
    variable before importing the cogs that depend on it.
    """
    for name in ("OWNER_GUILD_ID", "STATUS_ADMIN_GUILD_ID"):
        raw = os.getenv(name)
        if not raw:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0
