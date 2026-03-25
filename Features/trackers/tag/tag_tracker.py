import asyncio
from typing import Optional

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
        self._lock = asyncio.Lock()
        logger.info("TagTracker initialized")

    async def cog_load(self):
        """Start the tag check loop when the cog loads."""
        self.check_tags.start()
        logger.info("Tag tracker task started")

    def cog_unload(self):
        if self.check_tags.is_running():
            self.check_tags.cancel()

    async def _safe_fetch_user(self, user_id: int, max_retries: int = 3) -> Optional[discord.User]:
        """Fetch a user with 429 retry handling."""
        for attempt in range(max_retries):
            try:
                return await self.bot.fetch_user(user_id)
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 5.0)
                    logger.warning(f"Rate limited on fetch_user({user_id}), retrying in {retry_after}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_after)
                else:
                    raise
        logger.error(f"Failed to fetch user {user_id} after {max_retries} retries")
        return None

    async def _safe_role_change(self, member: discord.Member, role: discord.Role, *, add: bool):
        """Add or remove a role with 429 retry handling."""
        for attempt in range(3):
            try:
                if add:
                    await member.add_roles(role)
                else:
                    await member.remove_roles(role)
                return True
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 5.0)
                    logger.warning(f"Rate limited on role change for {member.name}, retrying in {retry_after}s")
                    await asyncio.sleep(retry_after)
                else:
                    raise
        return False

    @tasks.loop(hours=1)
    async def check_tags(self):
        if self._lock.locked():
            logger.info("Previous tag check still running, skipping this cycle.")
            return

        async with self._lock:
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

                logger.info(f"Checking tags in guild: {guild.name} ({len(guild.members)} members from cache)")
                for member in guild.members:
                    if member.bot:
                        continue

                    try:
                        user = await self._safe_fetch_user(member.id)
                        if user is None:
                            continue
                        if user.primary_guild and user.primary_guild.tag == server_tag:
                            if role not in member.roles:
                                await self._safe_role_change(member, role, add=True)
                                logger.info(f"Added role {role.name} to {member.name} for having the tag.")
                        else:
                            if role in member.roles:
                                await self._safe_role_change(member, role, add=False)
                                logger.info(f"Removed role {role.name} from {member.name} for not having the tag.")
                    except discord.errors.NotFound:
                        logger.warning(f"Could not fetch user profile for member {member.name} ({member.id}). Skipping.")
                    except Exception as e:
                        logger.error(f"An error occurred while checking tag for {member.name}: {e}")

                    await asyncio.sleep(1.5)

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
