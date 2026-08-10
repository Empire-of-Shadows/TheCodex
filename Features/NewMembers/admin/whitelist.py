import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime, timezone

from storage.settings.collections import db_manager
from storage.log import get_logger
from storage.settings.config_manager import get_config
from admin.setup_notice import permission_notice_embed

logger = get_logger("WhitelistManager")

# Configuration
WHITELIST_ROLE_NAME = "Whitelisted New Member"
WHITELIST_ROLE_COLOR = discord.Color.blue()
ACCOUNT_AGE_REQUIREMENT_DAYS = 90  # Must match the age check in joining.py


def has_whitelist_admin_app():
    """App command check for every whitelist command (read and mutation).

    Admin-only: Administrator permission or a configured Panel Access role.
    There is no moderator tier, so viewing and changing the screening whitelist
    are gated the same way.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False

        user = interaction.user

        perms = getattr(user, "guild_permissions", None)
        if perms and perms.administrator:
            return True

        guild_config = await get_config(interaction.guild.id)
        user_role_ids = {role.id for role in getattr(user, "roles", [])}
        admin_set = set(guild_config.roles["admin_role_ids"])

        return bool(user_role_ids & admin_set)

    return app_commands.check(predicate)


class WhitelistReasonModal(discord.ui.Modal, title="Whitelist Member"):
    """Modal for collecting the reason for whitelisting a member."""

    reason = discord.ui.TextInput(
        label="Reason for whitelisting",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this member being whitelisted? (e.g., Friend of active member, known from another community)",
        required=True,
        min_length=10,
        max_length=500
    )

    def __init__(self, cog, user_identifier: str, resolved_member: Optional[discord.Member] = None):
        super().__init__()
        self.cog = cog
        self.user_identifier = user_identifier
        self.resolved_member = resolved_member

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        await interaction.response.defer(ephemeral=True)

        # If we already resolved the member, use it; otherwise resolve now
        if self.resolved_member:
            result = await self.cog._add_to_whitelist_internal(
                interaction,
                self.resolved_member,
                str(self.reason)
            )
        else:
            result = await self.cog._add_to_whitelist_internal(
                interaction,
                self.user_identifier,
                str(self.reason)
            )

        if result['success']:
            embed = discord.Embed(
                title="✅ Member Whitelisted",
                description=result['message'],
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            if 'details' in result:
                embed.add_field(name="Details", value=result['details'], inline=False)
        else:
            embed = discord.Embed(
                title="❌ Whitelist Failed",
                description=result['message'],
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )

        embed.set_footer(text=f"Action by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)


@app_commands.default_permissions(manage_guild=True)
class WhitelistGroup(commands.GroupCog, name="whitelist", description="Manage member whitelist for age restrictions"):
    """
    Group cog providing:
    - /whitelist add <user> - Add a user to whitelist (opens modal for reason)
    - /whitelist remove <user> - Remove a user from whitelist

    Both act on one person and take a user argument, which is why they stayed
    commands. Browsing the list moved to the admin panel (New Members ->
    Whitelisted Members), and that replaced the old `list` and `check` commands:
    `list` capped out at 25 entries with no way past it, and once the panel shows
    everybody there is nothing left to look one person up for.

    ``default_permissions`` is what stops Discord listing these for every member.
    The real gate is still ``has_whitelist_admin_app`` below, which also honours
    Panel Access roles; this only sets the DEFAULT visibility. A server that
    grants Panel Access to a role without Manage Server can hand that role the
    commands under Server Settings -> Integrations.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("WhitelistGroup initialized")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Explain a denied whitelist command instead of a bare "unavailable".

        Every whitelist command is admin-tier, so the notice names the Panel
        Access role and where it is granted; only the verb differs between a
        mutation and a read.
        """
        if not isinstance(error, app_commands.CheckFailure):
            raise error

        command = getattr(interaction.command, "name", "")
        embed = await permission_notice_embed(
            interaction.guild,
            action=(
                "change the screening whitelist" if command in ("add", "remove")
                else "view the screening whitelist"
            ),
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.debug(f"Could not deliver whitelist permission notice: {e}")

    async def _ensure_whitelist_role(self, guild: discord.Guild) -> discord.Role:
        """Ensure the whitelist role exists, create if needed."""
        guild_config = await get_config(guild.id)
        role_name = guild_config.new_members["whitelist_role_name"]

        # Check by ID first, then by name
        if guild_config.new_members["whitelist_role_id"]:
            existing_role = guild.get_role(guild_config.new_members["whitelist_role_id"])
            if existing_role:
                return existing_role
        existing_role = discord.utils.get(guild.roles, name=role_name)
        if existing_role:
            return existing_role

        # Create the role
        try:
            role = await guild.create_role(
                name=role_name,
                color=WHITELIST_ROLE_COLOR,
                reason="Whitelist role for new members with new accounts",
                mentionable=False,
                hoist=True  # Display separately in member list
            )
            logger.info(f"Created whitelist role '{role_name}' in guild {guild.name}")
            return role
        except Exception as e:
            logger.error(f"Failed to create whitelist role: {e}")
            raise

    async def _resolve_user_identifier(self, guild: discord.Guild, identifier: str) -> Optional[tuple[int, str, bool]]:
        """
        Resolve a user identifier (ID or username) to (user_id, username, in_guild).

        Args:
            guild: The Discord guild
            identifier: User ID or username (case-sensitive)

        Returns:
            Tuple of (user_id, username, in_guild) or None if not found
        """
        # Try to parse as user ID
        try:
            user_id = int(identifier)
            # Try to find member in guild
            member = guild.get_member(user_id)
            if member:
                return (user_id, member.name, True)

            # Try to fetch user from Discord API
            try:
                user = await self.bot.fetch_user(user_id)
                return (user_id, user.name, False)
            except discord.NotFound:
                return None
            except Exception as e:
                logger.error(f"Error fetching user {user_id}: {e}")
                return None

        except ValueError:
            # Not a valid ID, treat as username (case-sensitive)
            username = identifier

            # Search in guild members first (case-sensitive)
            for member in guild.members:
                if member.name == username:  # Case-sensitive comparison
                    return (member.id, member.name, True)

            # Username not found in guild
            return None

    async def _add_to_whitelist_internal(self, interaction: discord.Interaction, user_or_id, reason: str) -> dict:
        """
        Internal method to add a user to the whitelist.

        Args:
            interaction: The interaction object
            user_or_id: Either a discord.Member, discord.User, user ID string, or username
            reason: The reason for whitelisting

        Returns:
            Dict with 'success', 'message', and optionally 'details'
        """
        guild = interaction.guild

        try:
            # Resolve the user
            if isinstance(user_or_id, (discord.Member, discord.User)):
                user_id = user_or_id.id
                username = user_or_id.name
                in_guild = isinstance(user_or_id, discord.Member)
                member = user_or_id if in_guild else None
            else:
                # String identifier (ID or username)
                resolution = await self._resolve_user_identifier(guild, str(user_or_id))
                if not resolution:
                    return {
                        'success': False,
                        'message': f"Could not find user: `{user_or_id}`\n\n"
                                   "**Tip:** Usernames are case-sensitive. Make sure you're using the exact username, "
                                   "or use the user ID instead."
                    }

                user_id, username, in_guild = resolution
                member = guild.get_member(user_id) if in_guild else None

            # Check if user is a bot
            if member and member.bot:
                return {
                    'success': False,
                    'message': "Cannot whitelist bot accounts."
                }

            # Get whitelist collection
            whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')

            # Check if already whitelisted (snowflake IDs are stored as strings)
            existing = await whitelist_collection.find_one({
                'guild_id': str(guild.id),
                'user_id': str(user_id)
            })

            if existing:
                if existing.get('is_active', True):
                    return {
                        'success': False,
                        'message': f"**{username}** (`{user_id}`) is already whitelisted.\n\n"
                                   f"Added by: <@{existing.get('added_by')}>\n"
                                   f"Date: <t:{int(existing.get('added_at').timestamp())}:F>\n"
                                   f"Reason: {existing.get('reason', 'No reason provided')}"
                    }
                else:
                    # Reactivate
                    await whitelist_collection.update_one(
                        {'guild_id': str(guild.id), 'user_id': str(user_id)},
                        {'$set': {
                            'is_active': True,
                            'reactivated_at': datetime.now(timezone.utc),
                            'reactivated_by': str(interaction.user.id),
                            'reactivated_reason': reason
                        }}
                    )
                    return {
                        'success': True,
                        'message': f"**{username}** (`{user_id}`) has been reactivated on the whitelist.",
                        'details': f"**Reason:** {reason}"
                    }

            # Add to whitelist
            whitelist_entry = {
                'guild_id': str(guild.id),
                'user_id': str(user_id),
                'username': username,
                'added_by': str(interaction.user.id),
                'added_by_username': interaction.user.name,
                'added_at': datetime.now(timezone.utc),
                'reason': reason,
                'is_active': True,
                'role_assigned': False,
                'role_assigned_at': None
            }

            await whitelist_collection.create_one(whitelist_entry)

            # If member is in guild and has a new account, assign the role
            role_assigned = False
            if member:
                guild_config = await get_config(guild.id)
                account_age = (datetime.now(timezone.utc) - member.created_at).days
                if account_age < guild_config.new_members["account_age_requirement_days"]:
                    try:
                        role = await self._ensure_whitelist_role(guild)
                        await member.add_roles(role, reason=f"Whitelisted by {interaction.user}")
                        role_assigned = True

                        # Update database with role info
                        await whitelist_collection.update_one(
                            {'guild_id': str(guild.id), 'user_id': str(user_id)},
                            {'$set': {
                                'role_assigned': True,
                                'role_assigned_at': datetime.now(timezone.utc),
                                'account_age_at_whitelist': account_age
                            }}
                        )
                        logger.info(f"Assigned whitelist role to {member} (account age: {account_age} days)")
                    except Exception as e:
                        logger.error(f"Failed to assign whitelist role: {e}")

            details = f"**User:** {username} (`{user_id}`)\n**Reason:** {reason}"
            if role_assigned:
                details += f"\n**Role Assigned:** Yes (account age: {account_age} days)"
            elif member:
                details += f"\n**Role Assigned:** No (account age: {(datetime.now(timezone.utc) - member.created_at).days} days - no role needed)"
            else:
                details += "\n**Role Assigned:** N/A (user not in server yet)"

            logger.info(f"User {username} ({user_id}) added to whitelist by {interaction.user} in guild {guild.name}")

            return {
                'success': True,
                'message': f"Successfully added **{username}** to the whitelist!",
                'details': details
            }

        except Exception as e:
            logger.error(f"Error adding to whitelist: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"An error occurred: {str(e)}"
            }

    @app_commands.command(name="add", description="Add a member to the whitelist (use User ID or exact username)")
    @app_commands.describe(user="The member to whitelist (User ID or exact username - case sensitive)")
    @has_whitelist_admin_app()
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, user: str):
        """Add a member to the whitelist with reason modal."""
        # First, try to resolve the user to provide better feedback
        resolution = await self._resolve_user_identifier(interaction.guild, user)

        if not resolution:
            embed = discord.Embed(
                title="❌ User Not Found",
                description=f"Could not find user: `{user}`\n\n"
                            "**Tips:**\n"
                            "• Usernames are case-sensitive\n"
                            "• Use the exact username or user ID\n"
                            "• User ID is more reliable than username",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_id, username, in_guild = resolution
        member = interaction.guild.get_member(user_id) if in_guild else None

        # Open modal for reason
        modal = WhitelistReasonModal(self, user, resolved_member=member or user_id)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="remove", description="Remove a member from the whitelist")
    @app_commands.describe(user="The member to remove (User ID or exact username - case sensitive)")
    @has_whitelist_admin_app()
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, user: str):
        """Remove a member from the whitelist."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        try:
            # Resolve user
            resolution = await self._resolve_user_identifier(guild, user)
            if not resolution:
                embed = discord.Embed(
                    title="❌ User Not Found",
                    description=f"Could not find user: `{user}`",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            user_id, username, in_guild = resolution
            member = guild.get_member(user_id) if in_guild else None

            # Get whitelist collection
            whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')

            # Check if whitelisted
            existing = await whitelist_collection.find_one({
                'guild_id': str(guild.id),
                'user_id': str(user_id)
            })

            if not existing or not existing.get('is_active', True):
                embed = discord.Embed(
                    title="❌ Not Whitelisted",
                    description=f"**{username}** (`{user_id}`) is not on the whitelist.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Remove from whitelist (soft delete)
            await whitelist_collection.update_one(
                {'guild_id': str(guild.id), 'user_id': str(user_id)},
                {'$set': {
                    'is_active': False,
                    'removed_at': datetime.now(timezone.utc),
                    'removed_by': str(interaction.user.id)
                }}
            )

            # Remove role if assigned
            role_removed = False
            if member and existing.get('role_assigned', False):
                try:
                    guild_config = await get_config(guild.id)
                    role = None
                    if guild_config.new_members["whitelist_role_id"]:
                        role = guild.get_role(guild_config.new_members["whitelist_role_id"])
                    if not role:
                        role = discord.utils.get(guild.roles, name=guild_config.new_members["whitelist_role_name"])
                    if role and role in member.roles:
                        await member.remove_roles(role, reason=f"Removed from whitelist by {interaction.user}")
                        role_removed = True
                        logger.info(f"Removed whitelist role from {member}")
                except Exception as e:
                    logger.error(f"Failed to remove whitelist role: {e}")

            details = f"**User:** {username} (`{user_id}`)"
            if role_removed:
                details += "\n**Role Removed:** Yes"

            embed = discord.Embed(
                title="✅ Removed from Whitelist",
                description=f"Successfully removed **{username}** from the whitelist.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Details", value=details, inline=False)
            embed.set_footer(text=f"Action by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            logger.info(f"User {username} ({user_id}) removed from whitelist by {interaction.user} in guild {guild.name}")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing from whitelist: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WhitelistGroup(bot))
