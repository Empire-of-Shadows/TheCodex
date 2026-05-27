import asyncio

import discord
from discord.ext import commands, tasks

from storage.config_manager import get_config, get_guild_config_manager
from utils.logger import get_logger

# Logger
logger = get_logger("tag_tracker")


class TagTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        logger.info("TagTracker initialized")

    async def cog_load(self):
        """Start the periodic reconcile loop when the cog loads."""
        self.check_tags.start()
        logger.info("Tag tracker task started")

    def cog_unload(self):
        if self.check_tags.is_running():
            self.check_tags.cancel()

    async def _safe_role_change(self, member: discord.Member, role: discord.Role, *, add: bool) -> bool:
        """Add or remove a role with 429 retry handling. Returns True on success."""
        for _attempt in range(3):
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

    async def _resolve_tag_settings(self, guild: discord.Guild):
        """Return (role, server_tag) if tag tracking is active for this guild, else None."""
        config = await get_config(guild.id)
        if not config.tag_tracker.get("enabled", False):
            return None
        server_tag = config.tag_tracker.get("server_tag")
        role_id = config.tag_tracker.get("role_id")
        if not server_tag or not role_id:
            return None
        role = guild.get_role(role_id)
        if not role:
            logger.warning(f"Tag role {role_id} not found in guild {guild.name}. Skipping.")
            return None
        return role, server_tag

    async def _sync_member(self, member: discord.Member, role: discord.Role, server_tag: str) -> bool:
        """Reconcile one member's tag role against their cached primary_guild tag.

        Reads ``member.primary_guild`` straight from the gateway-populated cache —
        no per-member ``fetch_user`` call — so a full sweep costs zero API calls
        in the steady state. Returns True if a role change was actually made.
        """
        if member.bot:
            return False

        primary = member.primary_guild
        has_tag = bool(primary and primary.tag == server_tag)
        has_role = role in member.roles

        if has_tag and not has_role:
            if await self._safe_role_change(member, role, add=True):
                logger.info(f"Added role {role.name} to {member.name} for having the tag.")
            return True
        if not has_tag and has_role:
            if await self._safe_role_change(member, role, add=False):
                logger.info(f"Removed role {role.name} from {member.name} for not having the tag.")
            return True
        return False

    @tasks.loop(hours=1)
    async def check_tags(self):
        """Periodic safety-net reconcile. Real-time updates flow through
        on_user_update; this catches anything the gateway missed."""
        if self._lock.locked():
            logger.info("Previous tag check still running, skipping this cycle.")
            return

        async with self._lock:
            logger.info("Starting tag check...")

            for guild in self.bot.guilds:
                settings = await self._resolve_tag_settings(guild)
                if not settings:
                    continue
                role, server_tag = settings

                logger.info(f"Checking tags in guild: {guild.name} ({len(guild.members)} members from cache)")
                for member in guild.members:
                    try:
                        changed = await self._sync_member(member, role, server_tag)
                        # Throttle ONLY when a role was actually mutated, so a
                        # converged server costs nothing and an initial rollout
                        # stays under the per-guild role rate limit.
                        if changed:
                            await asyncio.sleep(0.5)
                    except discord.HTTPException as e:
                        logger.error(f"HTTP error while checking tag for {member.name}: {e}")
                    except Exception as e:
                        logger.error(f"An error occurred while checking tag for {member.name}: {e}")

            logger.info("Tag check finished.")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Real-time tag sync when a user changes their primary (clan) guild.

        primary_guild is a user-global attribute, so the change surfaces as a
        user update rather than a member update. We compare tags (not object
        identity) to avoid resyncing on unrelated profile edits.
        """
        before_tag = before.primary_guild.tag if before.primary_guild else None
        after_tag = after.primary_guild.tag if after.primary_guild else None
        if before_tag == after_tag:
            return

        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is None:
                continue
            settings = await self._resolve_tag_settings(guild)
            if not settings:
                continue
            role, server_tag = settings
            try:
                await self._sync_member(member, role, server_tag)
            except discord.HTTPException as e:
                logger.error(f"Tag sync on user update failed for {after} in {guild.name}: {e}")

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
            mgr = await get_guild_config_manager()
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
