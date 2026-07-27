"""
Info Board

A static, admin-authored message posted to a channel that holds information, with
buttons and dropdowns that reveal *more* information privately to whoever clicks.

The board is posted once and then edited in place, so the channel never fills up
with duplicates - that logic lives in board_publisher and is shared with the admin
panel. Its interactions are routed by custom_id prefix through a plain listener
(see board_actions.dispatch_board_interaction), which is why a posted board keeps
working across restarts with nothing to re-register.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from Features.Board.board_actions import dispatch_board_interaction
from Features.Board.board_publisher import fetch_posted_message, publish
from Features.Board.board_schema import validate_board_schema
from Features.Board.board_store import board_store
from storage.log import get_logger
from storage.settings.config_manager import get_config

logger = get_logger("Board")


def has_board_permissions():
    """App command check: Administrator permission or a configured staff role."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False

        perms = getattr(interaction.user, "guild_permissions", None)
        if perms and perms.administrator:
            return True

        guild_config = await get_config(interaction.guild.id)
        user_role_ids = {role.id for role in getattr(interaction.user, "roles", [])}
        admin_set = set(guild_config.roles["admin_role_ids"])
        mod_set = set(guild_config.roles["mod_role_ids"])
        return bool(user_role_ids & (admin_set | mod_set))

    return app_commands.check(predicate)


class BoardGroup(commands.GroupCog, name="board", description="Info board commands"):
    """
    Group cog providing:
    - /board post [channel]
    - /board refresh
    - /board info
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("BoardGroup initialized")

    async def _publish_and_report(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Run a publish and turn the result into an ephemeral notice."""
        result = await publish(interaction.guild, channel)

        if not result.ok:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Board not published",
                    description=result.error,
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        description = result.summary
        if result.message is not None:
            description += f"\n[Jump to it]({result.message.jump_url})"

        logger.info(
            f"Board {result.action} by {interaction.user} ({interaction.user.id}) "
            f"in guild {interaction.guild.id}"
        )
        await interaction.followup.send(
            embed=discord.Embed(
                title=f"Board {result.action}",
                description=description,
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    # ── Commands ─────────────────────────────────────────────────────────────

    @app_commands.command(name="post", description="Post the info board to a channel")
    @app_commands.describe(channel="Channel to post the board in (defaults to this one)")
    @has_board_permissions()
    @app_commands.guild_only()
    async def post(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        target = channel or interaction.channel
        await self._publish_and_report(interaction, target)

    @app_commands.command(
        name="refresh", description="Update the posted info board with the latest layout"
    )
    @has_board_permissions()
    @app_commands.guild_only()
    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        # No channel: refresh wherever the board already lives.
        await self._publish_and_report(interaction, None)

    @app_commands.command(name="info", description="Show the status of the info board")
    @has_board_permissions()
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction):
        doc = await board_store.get_document(interaction.guild.id)
        board_data = (doc or {}).get("board_data")

        embed = discord.Embed(
            title="Info Board Status",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )

        if not board_data:
            embed.description = (
                "No board configured yet. Build one in the dashboard, or upload a "
                "JSON layout from **/admin -> Info Board -> Board Builder**."
            )
            embed.color = discord.Color.orange()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        valid, msg = validate_board_schema(board_data)
        embed.add_field(
            name="Layout",
            value=(
                f"{len(board_data.get('components', []))} block(s), "
                f"{len(board_store.list_responses(board_data))} private response(s)"
            ),
            inline=True,
        )
        embed.add_field(
            name="Valid",
            value="Yes" if valid else f"No - {msg[:200]}",
            inline=True,
        )

        message = await fetch_posted_message(interaction.guild, doc)
        if message is not None:
            embed.add_field(
                name="Posted",
                value=f"{message.channel.mention} - [jump]({message.jump_url})",
                inline=False,
            )
        elif (doc or {}).get("message_id"):
            embed.add_field(
                name="Posted",
                value="The stored message is gone. Use `/board refresh` to put it back.",
                inline=False,
            )
        else:
            embed.add_field(
                name="Posted",
                value="Not posted yet. Use `/board post`.",
                inline=False,
            )

        if (doc or {}).get("updated_at"):
            embed.set_footer(text="Layout last saved")
            embed.timestamp = doc["updated_at"]

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Unified error handler for the board command group."""
        try:
            if isinstance(error, app_commands.CheckFailure):
                embed = discord.Embed(
                    title="Permission Denied",
                    description=(
                        "You don't have permission to manage the info board.\n"
                        "Required: `Administrator` permission or a configured staff role."
                    ),
                    color=discord.Color.red(),
                )
            elif isinstance(error, app_commands.NoPrivateMessage):
                embed = discord.Embed(
                    title="Server only",
                    description="This command can only be used in a server.",
                    color=discord.Color.red(),
                )
            else:
                logger.error(f"Unhandled error in board commands: {error}", exc_info=True)
                embed = discord.Embed(
                    title="Unexpected Error",
                    description="An unexpected error occurred. Please try again later.",
                    color=discord.Color.red(),
                )

            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as inner_e:
            logger.error(f"Error in board cog error handler: {inner_e}", exc_info=True)


# ── Interaction routing ──────────────────────────────────────────────────────
# Registered as a plain listener rather than a branch in another feature's
# dispatcher, so the board owns its own routing (root CLAUDE.md: each feature is
# self-contained). add_listener is additive - it does not displace the guide or
# greeting routing that joining.py registers.

async def on_interaction(interaction: discord.Interaction):
    await dispatch_board_interaction(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoardGroup(bot))
    bot.add_listener(on_interaction, "on_interaction")
    logger.info("Board interaction listener registered")
