import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
import pytz
from discord.ext import commands, tasks

from storage.settings.collections import db_manager
from storage.settings.config_manager import get_guild_config_manager
from storage.log import get_logger

logger = get_logger("PrimeDrops")


def _sent_key(guild_id: int) -> str:
    """Mongo dotted-path field used to track when a drop was posted to a guild."""
    return f"sent_by_guild.{guild_id}"


class PrimeDrops(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.collection_manager = None
        self._posted_today: set[tuple[int, str]] = set()

    async def cog_load(self):
        logger.info("Loading PrimeDrops cog...")
        await self.initialize_drops_database()
        self.drops_tick.start()
        logger.info("PrimeDrops cog loaded successfully")

    async def cog_unload(self):
        logger.info("Unloading PrimeDrops cog...")
        self.drops_tick.cancel()
        logger.info("PrimeDrops cog unloaded")

    async def initialize_drops_database(self):
        try:
            await db_manager.initialize()
            self.collection_manager = db_manager.get_collection_manager('prime_drops')
            logger.info("Prime drops database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize prime drops database: {e}", exc_info=True)
            raise

    def _create_drop_embed(self, drop: Dict[str, Any]) -> discord.Embed:
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

    def _create_drop_embeds(
        self, drops: list[Dict[str, Any]], title: Optional[str] = None
    ) -> list[discord.Embed]:
        """Build a summary embed listing multiple drops. Used by the welcome browse flow."""
        if not drops:
            return []

        lines: list[str] = []
        for drop in drops:
            label = drop.get('label', 'Unknown Game')
            short_href = drop.get('short_href')
            expires = drop.get('expires')
            expires_str = ""
            if isinstance(expires, str) and expires:
                expires_str = f" · expires {expires}"
            elif isinstance(expires, datetime):
                expires_str = f" · expires {expires.strftime('%Y-%m-%d')}"
            if short_href:
                lines.append(f"- [{label}]({short_href}){expires_str}")
            else:
                lines.append(f"- **{label}**{expires_str}")

        description = "\n".join(lines[:25])  # cap to keep embed under 4096 chars

        embed = discord.Embed(
            title=title or "Free Gaming Drops",
            description=description or "No drops available right now.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Amazon Prime Gaming Drops")
        return [embed]

    async def _fetch_unsent_for_guild(self, guild_id: int) -> list[Dict[str, Any]]:
        if not self.collection_manager:
            return []
        return await self.collection_manager.find_many(
            {_sent_key(guild_id): {"$exists": False}},
            sort=[("expires", 1)],
        )

    async def _mark_sent_for_guild(
        self, guild_id: int, drops: list[Dict[str, Any]]
    ) -> None:
        now = datetime.now(timezone.utc)
        field = _sent_key(guild_id)
        for drop in drops:
            await self.collection_manager.update_one(
                {"_id": drop["_id"]},
                {"$set": {field: now}},
            )

    async def _post_drops_to_guild(
        self, guild_id: int, channel_id: int, drops: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Drops channel {channel_id} not found for guild {guild_id}")
            return []

        posted: list[Dict[str, Any]] = []
        for drop in drops:
            try:
                embed = self._create_drop_embed(drop)
                await channel.send(embed=embed)
                posted.append(drop)
                logger.info(f"Sent drop '{drop.get('label', 'Unknown')}' to guild {guild_id}")
                if len(posted) < len(drops):
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(
                    f"Failed to send drop '{drop.get('label', 'Unknown')}' to guild {guild_id}: {e}"
                )
        return posted

    async def send_drops_for_guild(self, guild_id: int, guild_config) -> int:
        """Post drops this guild has not yet received, and mark them sent to this guild."""
        if not self.collection_manager:
            logger.warning("Collection manager not initialized, skipping drops send")
            return 0

        channel_id = guild_config.drops.get("channel_id")
        if not channel_id:
            return 0

        drops = await self._fetch_unsent_for_guild(guild_id)
        if not drops:
            logger.info(f"No unsent drops for guild {guild_id}")
            return 0

        logger.info(f"Posting {len(drops)} drops to guild {guild_id}")
        posted = await self._post_drops_to_guild(guild_id, channel_id, drops)

        if posted:
            await self._mark_sent_for_guild(guild_id, posted)
            logger.info(f"Marked {len(posted)} drops as sent for guild {guild_id}")

        return len(posted)

    @tasks.loop(minutes=1)
    async def drops_tick(self):
        """Every minute, check if any guild is due for its scheduled drops post."""
        try:
            config_mgr = await get_guild_config_manager()
            guilds = await config_mgr.get_all_configured_guilds()

            today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self._posted_today = {
                k for k in self._posted_today if k[1] >= today_utc
            }

            for guild_id in guilds:
                try:
                    guild_config = await config_mgr.get_config(guild_id)
                    drops_cfg = guild_config.drops

                    if not drops_cfg.get("enabled", False):
                        continue
                    if not drops_cfg.get("channel_id"):
                        continue

                    hour = drops_cfg.get("post_hour", 6)
                    minute = drops_cfg.get("post_minute", 30)
                    tz_name = drops_cfg.get("timezone", "America/Chicago")

                    try:
                        tz = pytz.timezone(tz_name)
                    except pytz.UnknownTimeZoneError:
                        logger.warning(f"Unknown timezone '{tz_name}' for guild {guild_id}; skipping")
                        continue

                    now_local = datetime.now(tz)
                    today_key = (guild_id, now_local.strftime("%Y-%m-%d"))

                    if today_key in self._posted_today:
                        continue

                    if now_local.hour != hour or now_local.minute != minute:
                        continue

                    logger.info(
                        f"Scheduled drops post for guild {guild_id} "
                        f"({hour:02d}:{minute:02d} {tz_name})"
                    )
                    # Mark as posted only AFTER a successful send, so a send that raises
                    # isn't recorded as done (which would skip the guild for the day).
                    await self.send_drops_for_guild(guild_id, guild_config)
                    self._posted_today.add(today_key)

                except Exception as e:
                    logger.error(
                        f"Error processing drops for guild {guild_id}: {e}", exc_info=True
                    )
        except Exception as e:
            logger.error(f"Error in drops_tick: {e}", exc_info=True)

    @drops_tick.before_loop
    async def before_drops_tick(self):
        await self.bot.wait_until_ready()
        logger.info("Drops tick loop started (checks per-guild schedule every minute)")


async def setup(bot: commands.Bot):
    await bot.add_cog(PrimeDrops(bot))
