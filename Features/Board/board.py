"""
Info Board

A static, admin-authored message posted to a channel that holds information, with
buttons and dropdowns that reveal *more* information privately to whoever clicks.

The board is posted once and then edited in place, so the channel never fills up
with duplicates - that logic lives in board_publisher and is shared with the admin
panel. Its interactions are routed by custom_id prefix through a plain listener
(see board_actions.dispatch_board_interaction), which is why a posted board keeps
working across restarts with nothing to re-register.

**There are no board slash commands.** `/board post`, `/board refresh` and
`/board info` were retired: all three were admin-only, and the admin panel already
did the same work through **Info Board -> Post / Update Board** and **Info Board ->
Board Status**. Because they gated on a runtime check rather than
``default_permissions``, Discord could not hide them, so every member saw three
commands they were never allowed to run.

What remains here is the interaction listener. It is the whole reason this module
still exists as a cog: without it, every board already posted stops responding to
clicks.
"""

import discord
from discord.ext import commands

from Features.Board.board_actions import dispatch_board_interaction
from storage.log import get_logger

logger = get_logger("Board")


# ── Interaction routing ──────────────────────────────────────────────────────
# Registered as a plain listener rather than a branch in another feature's
# dispatcher, so the board owns its own routing (root CLAUDE.md: each feature is
# self-contained). add_listener is additive - it does not displace the guide or
# greeting routing that joining.py registers.

async def on_interaction(interaction: discord.Interaction):
    await dispatch_board_interaction(interaction)


async def setup(bot: commands.Bot):
    bot.add_listener(on_interaction, "on_interaction")
    logger.info("Board interaction listener registered")
