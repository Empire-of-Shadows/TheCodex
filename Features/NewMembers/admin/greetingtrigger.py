import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from Features.NewMembers.joining import guild_handler
from Features.NewMembers.greeting_schema import validate_greeting_schema
from storage.log import get_logger
from storage.settings.config_manager import get_config

logger = get_logger("GreetingTrigger")


def has_greeting_permissions_app():
    """App command check for greeting message permissions."""
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


class GreetingGroup(commands.GroupCog, name="greeting", description="Greeting system commands"):
    """
    Group cog providing:
    - /greeting test [member]
    - /greeting info
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.handler = guild_handler
        logger.info("GreetingGroup initialized")

    @app_commands.command(name="test", description="Test the greeting message system for a member (default: you)")
    @app_commands.describe(member="Member to test the greeting message for")
    @has_greeting_permissions_app()
    @app_commands.guild_only()
    async def test(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Slash command to test the greeting message."""
        target_member = member or interaction.user

        # Quick confirmation (ephemeral)
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except discord.InteractionResponded:
            pass

        # Validate greeting config before attempting to render
        guild_config = await get_config(interaction.guild.id)
        greeting_components = guild_config.new_members.get("greeting_components")

        if not greeting_components:
            embed = discord.Embed(
                title="❌ Greeting Config Validation Failed",
                description="No greeting components configured.\nUse the greeting builder to create a config first.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        valid, msg = validate_greeting_schema(greeting_components)
        if not valid:
            embed = discord.Embed(
                title="❌ Greeting Config Validation Failed",
                description=f"Your greeting JSON config has an error:\n```{msg}```",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            # Perform the greeting action
            await self.handler.send_greeting_message(target_member)

            # Log the action
            logger.info(
                f"Greeting test triggered by {interaction.user} ({interaction.user.id}) "
                f"for {target_member} ({target_member.id})"
            )

            # Success confirmation
            embed = discord.Embed(
                title="✅ Greeting Message Test Complete",
                description=f"Greeting message sent for {target_member.mention}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error during greeting message test: {e}", exc_info=True)

            error_embed = discord.Embed(
                title="❌ Greeting Message Test Failed",
                description=f"An error occurred while testing the greeting message:\n```{str(e)[:1000]}```",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            error_embed.set_footer(text=f"Tested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            if interaction.followup:
                await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(name="info", description="Show information about the greeting system")
    @has_greeting_permissions_app()
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction):
        """Slash command to show greeting system information."""
        # Get guild config for dynamic settings
        guild_config = await get_config(interaction.guild.id)

        embed = discord.Embed(
            title="🔧 Greeting System Information",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        # Get greeting channel from config
        greeting_channel = self.bot.get_channel(guild_config.new_members["greeting_channel_id"]) if guild_config.new_members["greeting_channel_id"] else None

        embed.add_field(
            name="Greeting Channel",
            value=greeting_channel.mention if isinstance(greeting_channel, (discord.TextChannel, discord.Thread)) else "❌ Not configured",
            inline=True
        )

        embed.add_field(
            name="Account Age Requirement",
            value=f"{guild_config.new_members['account_age_requirement_days']} days",
            inline=True
        )

        embed.add_field(
            name="Commands Available",
            value="`/greeting test` - Test the greeting message\n`/greeting info` - Show this info",
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
        """Unified error handler for the greeting command group."""
        try:
            if isinstance(error, app_commands.CheckFailure):
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="You don't have permission to use greeting commands.\n"
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
                logger.error(f"Unhandled error in greeting commands: {error}", exc_info=True)
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
            logger.error(f"Error in greeting cog error handler: {inner_e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GreetingGroup(bot))