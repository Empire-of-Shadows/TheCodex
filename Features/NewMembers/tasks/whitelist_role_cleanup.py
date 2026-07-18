import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
from typing import List

from storage.manager import db_manager
from storage.log import get_logger
from storage.config_manager import get_config

logger = get_logger("WhitelistRoleCleanup")


class WhitelistRoleCleanupTask(commands.Cog):
    """
    Background task to automatically remove the whitelist role from members
    whose accounts have aged past the requirement threshold.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.whitelist_collection = None
        logger.info("WhitelistRoleCleanupTask initialized")

    async def cog_load(self):
        """Initialize database when cog loads"""
        logger.info("Loading WhitelistRoleCleanupTask cog...")
        await self.initialize_database()

        # Start the cleanup task after database is initialized
        self.cleanup_whitelist_roles.start()
        logger.info("WhitelistRoleCleanupTask cog loaded successfully")

    async def initialize_database(self):
        """Initialize the database connection"""
        try:
            # Ensure database manager is initialized
            await db_manager.initialize()

            # Get the whitelist collection manager
            self.whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')

            logger.info("Whitelist database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize whitelist database: {e}", exc_info=True)
            raise

    def cog_unload(self):
        """Stop the task when the cog is unloaded."""
        self.cleanup_whitelist_roles.cancel()

    @tasks.loop(hours=1)  # Run every hour
    async def cleanup_whitelist_roles(self):
        """
        Check all whitelisted members with roles and remove the role if their
        account is now old enough.
        """
        try:
            logger.info("Starting whitelist role cleanup task")

            # Check if database is initialized
            if not self.whitelist_collection:
                logger.warning("Whitelist collection not initialized, skipping cleanup")
                return

            # Find all active whitelist entries with roles assigned
            entries = await self.whitelist_collection.find_many({
                'is_active': True,
                'role_assigned': True
            })

            if not entries:
                logger.debug("No whitelisted members with roles to check")
                return

            total_checked = 0
            total_removed = 0
            errors = 0

            for entry in entries:
                try:
                    guild_id = entry.get('guild_id')
                    user_id = entry.get('user_id')
                    username = entry.get('username', 'Unknown')

                    # Get guild
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        logger.debug(f"Guild {guild_id} not found, skipping")
                        continue

                    # Get per-guild config
                    guild_config = await get_config(guild_id)

                    # Get member
                    member = guild.get_member(user_id)
                    if not member:
                        # Member left the guild, mark role as not assigned
                        await self.whitelist_collection.update_one(
                            {'guild_id': guild_id, 'user_id': user_id},
                            {'$set': {'role_assigned': False}}
                        )
                        logger.debug(f"Member {username} ({user_id}) left guild, marked role as unassigned")
                        continue

                    # Check account age
                    account_age_days = (datetime.now(timezone.utc) - member.created_at).days

                    total_checked += 1

                    # If account is now old enough, remove the role
                    if account_age_days >= guild_config.new_members["account_age_requirement_days"]:
                        # Get the role (prefer ID, fallback to name)
                        role = None
                        if guild_config.new_members["whitelist_role_id"]:
                            role = guild.get_role(guild_config.new_members["whitelist_role_id"])
                        if not role:
                            role = discord.utils.get(guild.roles, name=guild_config.new_members["whitelist_role_name"])
                        if role and role in member.roles:
                            try:
                                await member.remove_roles(role, reason=f"Account aged out ({account_age_days} days old)")
                                logger.info(f"Removed whitelist role from {member} (account age: {account_age_days} days)")
                            except Exception as role_error:
                                logger.error(f"Failed to remove role from {member}: {role_error}")
                                errors += 1
                                continue

                        # Update database
                        await self.whitelist_collection.update_one(
                            {'guild_id': guild_id, 'user_id': user_id},
                            {'$set': {
                                'role_assigned': False,
                                'role_removed_at': datetime.now(timezone.utc),
                                'role_removed_reason': 'account_aged_out',
                                'account_age_at_removal': account_age_days
                            }}
                        )

                        total_removed += 1
                        logger.info(f"Updated database for {username} ({user_id}) - role removed due to age")

                        # Optionally send a DM to the member
                        try:
                            embed = discord.Embed(
                                title="🎉 Account Age Requirement Met!",
                                description=f"Your Discord account is now {account_age_days} days old and meets our server's age requirement.\n\n"
                                            f"The **{guild_config.new_members['whitelist_role_name']}** role has been removed as it's no longer needed. "
                                            f"You now have full access to the server!\n\n"
                                            f"Thank you for being part of our community! 🙏",
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            embed.set_footer(text=f"{guild.name}", icon_url=guild.icon.url if guild.icon else None)
                            await member.send(embed=embed)
                            logger.info(f"Sent DM notification to {member}")
                        except discord.Forbidden:
                            logger.debug(f"Could not send DM to {member} (Forbidden)")
                        except Exception as dm_error:
                            logger.warning(f"Failed to send DM to {member}: {dm_error}")

                except Exception as entry_error:
                    logger.error(f"Error processing whitelist entry: {entry_error}", exc_info=True)
                    errors += 1
                    continue

            logger.info(
                f"Whitelist role cleanup complete: "
                f"Checked {total_checked}, Removed {total_removed}, Errors {errors}"
            )

        except Exception as e:
            logger.error(f"Error in whitelist role cleanup task: {e}", exc_info=True)

    @cleanup_whitelist_roles.before_loop
    async def before_cleanup(self):
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.info("Bot ready, whitelist role cleanup task will now run")


async def setup(bot: commands.Bot):
    await bot.add_cog(WhitelistRoleCleanupTask(bot))
