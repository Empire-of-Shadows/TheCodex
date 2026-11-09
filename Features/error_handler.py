"""Global application-command error handler for TheCodex.

Registers a single `CommandTree.on_error` so that unhandled slash-command and
interaction errors are logged with context and surfaced to the user as a clean
ephemeral message instead of Discord's bare "interaction failed".

A few cogs define their own `cog_app_command_error` (or per-command error
handlers). discord.py calls those first and then this tree handler for the same
error, so a local handler that has already told the member what went wrong marks
the interaction with `mark_error_handled`; this handler then stays silent instead
of stacking a second, vaguer message on top. As a second guard (since 2026-11-07)
the member reply is also skipped whenever the failing command has any local
handler at all (``Command._has_any_error_handlers``, the check discord.py's own
default ``tree.on_error`` uses), so every local handler must answer on every path
it handles. The log line is still written either way.

Expected refusals (cooldown, missing permissions, a failed check, a Discord
permission refusal) get a plain reason; only an unexpected failure ends with the
support-server line from ``commands/help/help_content.py``. A failed check that
already answered the member gets no second reply.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from commands.help.help_content import SUPPORT_LINE
from storage.log import get_logger

logger = get_logger("ErrorHandler")

#: Key a local error handler sets in ``interaction.extras`` once it has answered.
ERROR_HANDLED_KEY = "codex_error_handled"


def mark_error_handled(interaction: discord.Interaction) -> None:
    """Record that a local handler already answered this failed interaction."""
    try:
        interaction.extras[ERROR_HANDLED_KEY] = True
    except Exception:  # pragma: no cover - extras is a plain dict on every Interaction
        pass


class ErrorHandler(commands.Cog):
    """Installs a global app-command error handler on the command tree."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._previous = bot.tree.on_error
        bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self):
        # Restore whatever handler was in place before this cog loaded.
        self.bot.tree.on_error = self._previous

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        original = getattr(error, "original", error)

        # A cog or command handler already explained this one to the member.
        if interaction.extras.get(ERROR_HANDLED_KEY):
            return

        if isinstance(error, app_commands.CommandOnCooldown):
            await self._respond(
                interaction,
                "Slow down",
                f"This command is on cooldown. Try again in "
                f"**{round(error.retry_after, 1)}** seconds.",
                discord.Color.orange(),
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            await self._respond(
                interaction,
                "Missing Permissions",
                f"You need the following permissions:\n**{perms}**",
            )
            return

        if isinstance(error, app_commands.BotMissingPermissions):
            perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            logger.warning(f"Bot missing permissions in guild {interaction.guild_id}: {perms}")
            await self._respond(
                interaction,
                "Bot Missing Permissions",
                f"I need the following permissions to do this:\n**{perms}**\n\n"
                "Please ask a server administrator to grant them.",
            )
            return

        if isinstance(error, app_commands.CheckFailure):
            # Most checks already sent their own response; only fill the gap.
            if not interaction.response.is_done():
                await self._respond(
                    interaction,
                    "Command Unavailable",
                    "This command cannot be used right now.",
                    discord.Color.orange(),
                )
            return

        if isinstance(error, app_commands.CommandNotFound):
            logger.debug(f"Command not found: {getattr(interaction.command, 'qualified_name', 'unknown')}")
            return

        # Stale interaction (404 Unknown interaction) - nothing we can send.
        if isinstance(original, discord.NotFound) and getattr(original, "code", None) == 10062:
            logger.debug("Interaction expired before a response could be sent")
            return

        if isinstance(original, discord.Forbidden):
            logger.warning(f"Forbidden in guild {interaction.guild_id}: {original}")
            await self._respond(
                interaction,
                "Permission Denied",
                "I don't have permission to do that. Please check my role and "
                "channel permissions.",
            )
            return

        # Anything else is unexpected: log with full context + stack trace.
        logger.error(
            "Unhandled command error: %s: %s",
            type(original).__name__,
            original,
            extra={
                "guild_id": interaction.guild_id,
                "user_id": getattr(interaction.user, "id", None),
                "command": getattr(interaction.command, "qualified_name", None),
            },
            exc_info=original,
        )
        await self._respond(
            interaction,
            "Something went wrong",
            "An unexpected error occurred. It has been logged and will be "
            "investigated. Please try again in a moment."
            # In the description, not a footer: footers cannot render links.
            f"\n\n{SUPPORT_LINE}",
        )

    @staticmethod
    def _answered_by_own_handler(interaction: discord.Interaction) -> bool:
        """True when the failing command has its own error handler, which has replied.

        discord.py 2.7 runs the command's own ``on_error`` (``@cmd.error``), an
        overridden parent or grandparent ``Group.on_error``, and the cog's overridden
        ``cog_app_command_error`` BEFORE ``tree.on_error``, so a reply here as well
        answers the member twice. ``Command._has_any_error_handlers`` is the exact
        check discord.py's default ``tree.on_error`` uses to stay quiet, and it covers
        all three. Any such handler in this bot must reply on every path it handles.
        If the check is unavailable, reply anyway - a second message is better than
        none.
        """
        command = getattr(interaction, "command", None)
        check = getattr(command, "_has_any_error_handlers", None)
        if check is None:
            return False
        try:
            return bool(check())
        except Exception:
            return False

    async def _respond(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: discord.Color = discord.Color.red(),
    ):
        """Send an ephemeral error embed to the member. Never raises.

        Skipped when the command's own error handler already answered. Every
        command in this bot answers or defers ephemerally, so a followup after a
        defer stays private too.
        """
        if self._answered_by_own_handler(interaction):
            return
        embed = discord.Embed(title=title, description=description, color=color)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            # The interaction may have expired. Nothing more we can do; don't
            # mask the original error.
            logger.debug(f"Could not deliver error response: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
