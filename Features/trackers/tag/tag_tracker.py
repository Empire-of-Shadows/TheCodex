import asyncio

import discord
from discord.ext import commands, tasks
import logging

from storage.config_manager import get_config
from utils.logger import get_logger

# Logger
logger = get_logger("tag_tracker")

class TagTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("TagTracker initialized")

    async def cog_load(self):
        """Start the tag check loop when the cog loads."""
        self.check_tags.start()
        logger.info("Tag tracker task started")

    def cog_unload(self):
        if self.check_tags.is_running():
            self.check_tags.cancel()

    @tasks.loop(minutes=5)
    async def check_tags(self):
        logger.info("Starting tag check...")

        for guild in self.bot.guilds:
            config = await get_config(guild.id)

            if not config.tag_tracker["enabled"]:
                logger.debug(f"Tag tracker disabled for guild {guild.name}, skipping.")
                continue

            server_tag = config.tag_tracker["server_tag"]
            role_id = config.tag_tracker["role_id"]

            if not server_tag or not role_id:
                logger.warning(f"Server tag or role ID not configured for guild {guild.name}. Skipping.")
                continue

            role = guild.get_role(role_id)
            if not role:
                logger.warning(f"Role with ID {role_id} not found in guild {guild.name}. Skipping.")
                continue

            logger.info(f"Checking tags in guild: {guild.name}")
            async for member in guild.fetch_members(limit=None):
                if member.bot:
                    continue

                try:
                    user = await self.bot.fetch_user(member.id)
                    if user.primary_guild and user.primary_guild.tag == server_tag:
                        if role not in member.roles:
                            await member.add_roles(role)
                            logger.info(f"Added role {role.name} to {member.name} for having the tag.")
                    else:
                        if role in member.roles:
                            await member.remove_roles(role)
                            logger.info(f"Removed role {role.name} from {member.name} for not having the tag.")
                except discord.errors.NotFound:
                    logger.warning(f"Could not fetch user profile for member {member.name} ({member.id}). Skipping.")
                except Exception as e:
                    logger.error(f"An error occurred while checking tag for {member.name}: {e}")

                await asyncio.sleep(1)

        logger.info("Tag check finished.")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Auto-sync the server tag when the guild's clan tag changes."""
        try:
            data = await self.bot.http.get_guild(after.id)
            clan = data.get("clan")
            new_tag = clan.get("tag") if clan else None
        except Exception as e:
            logger.error(f"Failed to fetch clan tag on guild update for {after.name}: {e}")
            return

        config = await get_config(after.id)
        current_tag = config.tag_tracker.get("server_tag")

        if new_tag and new_tag != current_tag:
            from storage.config_manager import get_guild_config_manager
            mgr = get_guild_config_manager()
            config.tag_tracker["server_tag"] = new_tag
            await mgr.save_config(config)
            logger.info(f"Auto-updated server tag for {after.name}: {current_tag!r} -> {new_tag!r}")
        elif not new_tag and current_tag:
            logger.warning(f"Server {after.name} removed their clan tag. Tag tracker still configured with: {current_tag!r}")

    @check_tags.before_loop
    async def before_check_tags(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    cog = TagTracker(bot)
    await bot.add_cog(cog)
