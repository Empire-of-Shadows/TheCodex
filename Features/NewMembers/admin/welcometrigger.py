import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from Features.NewMembers.joining import guild_handler
from Features.NewMembers.welcome_schema import validate_welcome_schema
from storage.log import get_logger
from storage.settings.config_manager import get_config

logger = get_logger("WelcomeTrigger")


def has_welcome_permissions_app():
    """App command check for welcome message permissions."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False

        user = interaction.user

        # Check if user has administrator permission
        perms = getattr(user, "guild_permissions", None)
        if perms and perms.administrator:
            return True

        # Get guild config for dynamic role checks
        guild_config = await get_config(interaction.guild.id)

        # Check for admin or moderator roles from config
        user_role_ids = {role.id for role in getattr(user, "roles", [])}
        admin_set = set(guild_config.roles["admin_role_ids"])
        mod_set = set(guild_config.roles["mod_role_ids"])

        return bool(user_role_ids & (admin_set | mod_set))

    return app_commands.check(predicate)


class WelcomeGroup(commands.GroupCog, name="welcome", description="Welcome system commands"):
    """
    Group cog providing:
    - /welcome test [member]
    - /welcome info
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.handler = guild_handler
        logger.info("WelcomeGroup initialized")

    @app_commands.command(name="test", description="Test the welcome message system for a member (default: you)")
    @app_commands.describe(member="Member to test the welcome message for")
    @has_welcome_permissions_app()
    @app_commands.guild_only()
    async def test(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Slash command to test welcome message."""
        target_member = member or interaction.user

        # Quick confirmation (ephemeral)
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except discord.InteractionResponded:
            pass

        # Validate welcome config before attempting to render
        guild_config = await get_config(interaction.guild.id)
        welcome_components = guild_config.new_members.get("welcome_components")

        if not welcome_components:
            embed = discord.Embed(
                title="❌ Welcome Config Validation Failed",
                description="No welcome components configured.\nUse the welcome builder to create a config first.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        valid, msg = validate_welcome_schema(welcome_components)
        if not valid:
            embed = discord.Embed(
                title="❌ Welcome Config Validation Failed",
                description=f"Your welcome JSON config has an error:\n```{msg}```",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            # Perform the welcome action
            await self.handler.send_welcome_message(target_member)

            # Log the action
            logger.info(
                f"Welcome test triggered by {interaction.user} ({interaction.user.id}) "
                f"for {target_member} ({target_member.id})"
            )

            # Success confirmation
            embed = discord.Embed(
                title="✅ Welcome Message Test Complete",
                description=f"Welcome message sent for {target_member.mention}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error during welcome message test: {e}", exc_info=True)

            error_embed = discord.Embed(
                title="❌ Welcome Message Test Failed",
                description=f"An error occurred while testing the welcome message:\n```{str(e)[:1000]}```",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            error_embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            if interaction.followup:
                await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(name="info", description="Show information about the welcome system")
    @has_welcome_permissions_app()
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction):
        """Slash command to show welcome system information."""
        # Get guild config for dynamic settings
        guild_config = await get_config(interaction.guild.id)

        embed = discord.Embed(
            title="🔧 Welcome System Information",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        # Get welcome channel from config
        welcome_channel = self.bot.get_channel(guild_config.new_members["welcome_channel_id"]) if guild_config.new_members["welcome_channel_id"] else None

        embed.add_field(
            name="Welcome Channel",
            value=welcome_channel.mention if isinstance(welcome_channel, (discord.TextChannel, discord.Thread)) else "❌ Not configured",
            inline=True
        )

        embed.add_field(
            name="Account Age Requirement",
            value=f"{guild_config.new_members['account_age_requirement_days']} days",
            inline=True
        )

        embed.add_field(
            name="Commands Available",
            value="`/welcome test` - Test welcome message\n`/welcome info` - Show this info",
            inline=False
        )

        # Build dynamic role list
        role_mentions = ["• `Administrator` permission"]
        for role_id in guild_config.roles["admin_role_ids"]:
            role_mentions.append(f"• <@&{role_id}>")
        for role_id in guild_config.roles["mod_role_ids"]:
            role_mentions.append(f"• <@&{role_id}>")

        if len(role_mentions) == 1:
            role_mentions.append("• *No staff roles configured*")

        embed.add_field(
            name="Required Permissions",
            value="\n".join(role_mentions),
            inline=False
        )

        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Unified error handler for the welcome command group."""
        try:
            if isinstance(error, app_commands.CheckFailure):
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="You don't have permission to use welcome commands.\n"
                                "Required: `Administrator` permission or a configured staff role.\n"
                                "Use `/config view` to see configured roles.",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)

            elif isinstance(error, app_commands.CommandOnCooldown):
                embed = discord.Embed(
                    title="⏳ Cooldown Active",
                    description=f"Please wait {int(getattr(error, 'retry_after', 10))} seconds before trying again.",
                    color=discord.Color.orange()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)

            elif isinstance(error, app_commands.NoPrivateMessage):
                if interaction.response.is_done():
                    await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)

            else:
                logger.error(f"Unhandled error in welcome commands: {error}", exc_info=True)
                embed = discord.Embed(
                    title="❌ Unexpected Error",
                    description="An unexpected error occurred. Please try again later.",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as inner_e:
            logger.error(f"Error in welcome cog error handler: {inner_e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeGroup(bot))