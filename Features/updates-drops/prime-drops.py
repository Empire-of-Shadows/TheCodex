import asyncio
from datetime import datetime, timezone, time, timedelta
from typing import List, Dict, Any

import discord
from discord.ext import commands, tasks
import pytz

from storage.database_manager import db_manager
from utils.logger import get_logger
from storage.config_manager import get_config, get_guild_config_manager

logger = get_logger("PrimeDrops")

# Configuration
CHICAGO_TZ = pytz.timezone('America/Chicago')
CHICAGO_TIME = time(6, 30)
UTC_TIME = datetime.combine(datetime.today(), CHICAGO_TIME)
UTC_TIME = CHICAGO_TZ.localize(UTC_TIME).astimezone(pytz.UTC).time()
SEND_TIME = UTC_TIME
GRACE_PERIOD_MINUTES = 20


class PrimeDrops(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.collection_manager = None


    async def cog_load(self):
        """Initialize database when cog loads"""
        logger.info("Loading PrimeDrops cog...")
        await self.initialize_drops_database()

        # Start the daily task
        self.daily_drops_check.start()

        # Check if we missed today's scheduled run but are still within the grace window
        self.bot.loop.create_task(self.check_missed_drops_run())

        logger.info("PrimeDrops cog loaded successfully")

    async def cog_unload(self):
        """Cleanup when cog unloads"""
        logger.info("Unloading PrimeDrops cog...")
        self.daily_drops_check.cancel()
        logger.info("PrimeDrops cog unloaded")

    async def initialize_drops_database(self):
        """Initialize the drops database connection"""
        try:
            # Ensure database manager is initialized
            await db_manager.initialize()

            # Get the prime drops collection manager
            self.collection_manager = db_manager.get_collection_manager('prime_drops')

            logger.info("Prime drops database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize prime drops database: {e}", exc_info=True)
            raise

    async def check_missed_drops_run(self):
        """
        On startup/reconnect, if we're within GRACE_PERIOD_MINUTES after today's scheduled send time
        and no recent bot message is found in any drops channel, run the drops check once.
        """
        try:
            await self.bot.wait_until_ready()

            now_utc = datetime.now(timezone.utc)

            # Today's scheduled send datetime in UTC
            today_send_dt = datetime.combine(now_utc.date(), SEND_TIME).replace(tzinfo=pytz.UTC)
            grace_end = today_send_dt + timedelta(minutes=GRACE_PERIOD_MINUTES)

            # Only act if we are within the grace window
            if not (today_send_dt <= now_utc <= grace_end):
                logger.info("Not within grace window for missed drops run; skipping catch-up check.")
                return

            if not self.bot.user:
                logger.warning("Bot user not available yet; skipping missed-run check")
                return

            # Get all configured guilds and check their drops channels
            config_manager = await get_guild_config_manager()
            configured_guilds = await config_manager.get_all_configured_guilds()

            found_recent_message = False
            for guild_id in configured_guilds:
                guild_config = await config_manager.get_config(guild_id)

                if not guild_config.drops.get("enabled", False):
                    continue

                if not guild_config.drops["channel_id"]:
                    continue

                channel = self.bot.get_channel(guild_config.drops["channel_id"])
                if not channel:
                    continue

                # Look for a recent message from this bot in the channel after today's scheduled time
                async for message in channel.history(limit=50):
                    if message.author.id != self.bot.user.id:
                        continue

                    message_time = message.created_at.replace(tzinfo=timezone.utc)
                    if message_time >= today_send_dt:
                        found_recent_message = True
                        break

                if found_recent_message:
                    break

            if found_recent_message:
                logger.info(
                    "Recent drops message from bot found within today's window; "
                    "skipping missed-run catch-up."
                )
                return

            logger.info(
                "Within grace window and no recent drops message found; "
                "running missed daily_drops_check now."
            )
            await self.daily_drops_check()
        except Exception as e:
            logger.error(f"Error during missed drops run check: {e}", exc_info=True)

    def _create_drop_embed(self, drop: Dict[str, Any]) -> discord.Embed:
        """Create an embed for a single drop (used by daily_drops_check to post to channels)."""
        embed = discord.Embed(
            title=drop.get('label', 'Unknown Game'),
            description=drop.get('description', 'No description available'),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        image_url = drop.get('image_url')
        if image_url:
            embed.set_thumbnail(url=image_url)

        expires = drop.get('expires')
        if expires:
            if isinstance(expires, str):
                embed.add_field(name="Expires", value=expires, inline=True)
            elif isinstance(expires, datetime):
                embed.add_field(name="Expires", value=expires.strftime("%Y-%m-%d %H:%M UTC"), inline=True)

        genres = drop.get('genres')
        if genres:
            embed.add_field(name="Genres", value=genres, inline=True)

        publisher = drop.get('publisher')
        if publisher:
            embed.add_field(name="Publisher", value=publisher, inline=True)

        short_href = drop.get('short_href')
        if short_href:
            embed.add_field(name="Claim Here", value=f"[Get Free Game]({short_href})", inline=True)

        embed.set_footer(text="Amazon Prime Gaming Drops")

        return embed

    @tasks.loop(time=SEND_TIME)
    async def daily_drops_check(self):
        """Daily task to check and send unsent drops to all configured guilds"""
        try:
            logger.info("Running daily drops check...")

            if not self.collection_manager:
                logger.warning("Collection manager not initialized, skipping drops check")
                return

            unsent_drops = await self.collection_manager.find_many(
                {"sent": {"$ne": True}},
                sort=[("expires", 1)]
            )

            if not unsent_drops:
                logger.info("No unsent drops found")
                return

            logger.info(f"Found {len(unsent_drops)} unsent drops")

            # Get guild config manager to iterate through all configured guilds
            config_manager = await get_guild_config_manager()
            configured_guilds = await config_manager.get_all_configured_guilds()

            guilds_posted = 0
            for guild_id in configured_guilds:
                try:
                    guild_config = await config_manager.get_config(guild_id)

                    if not guild_config.drops.get("enabled", False):
                        logger.debug(f"Drops disabled for guild {guild_id}, skipping")
                        continue

                    # Skip if no drops channel configured
                    if not guild_config.drops["channel_id"]:
                        logger.debug(f"No drops channel configured for guild {guild_id}, skipping")
                        continue

                    channel = self.bot.get_channel(guild_config.drops["channel_id"])
                    if not channel:
                        logger.warning(f"Drops channel {guild_config.drops['channel_id']} not found for guild {guild_id}")
                        continue

                    sent_count = 0
                    for drop in unsent_drops:
                        try:
                            embed = self._create_drop_embed(drop)
                            await channel.send(embed=embed)
                            sent_count += 1
                            logger.info(f"Sent drop '{drop.get('label', 'Unknown')}' to guild {guild_id}")

                            # Rate limiting - wait 1 second between sends
                            if sent_count < len(unsent_drops):
                                await asyncio.sleep(1)

                        except Exception as e:
                            logger.error(f"Failed to send drop '{drop.get('label', 'Unknown')}' to guild {guild_id}: {e}")
                            continue

                    guilds_posted += 1

                except Exception as guild_error:
                    logger.error(f"Error posting drops to guild {guild_id}: {guild_error}", exc_info=True)
                    continue

            # Mark drops as sent only if we posted to at least one guild
            if guilds_posted > 0:
                for drop in unsent_drops:
                    await self.collection_manager.update_one(
                        {"_id": drop["_id"]},
                        {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc)}}
                    )

                logger.info(f"Daily drops check completed. Sent {len(unsent_drops)} drops to {guilds_posted} guild(s).")
            else:
                logger.warning("No guilds have drops channels configured - drops not sent")

        except Exception as e:
            logger.error(f"Error in daily drops check: {e}", exc_info=True)

    @daily_drops_check.before_loop
    async def before_daily_drops_check(self):
        """Wait for bot to be ready before starting daily task"""
        await self.bot.wait_until_ready()
        logger.info(f"Daily drops check scheduled for 6:00 AM Chicago time (UTC: {SEND_TIME})")


async def setup(bot: commands.Bot):
    await bot.add_cog(PrimeDrops(bot))
