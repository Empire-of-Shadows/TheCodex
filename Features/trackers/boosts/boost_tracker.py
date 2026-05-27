import asyncio
import discord
from discord.ext import commands
import datetime

from storage.database_manager import db_manager
from storage.config_manager import get_config
from utils.logger import get_logger

logger = get_logger("BoostTracker")


class BoostTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = db_manager
        self._reconcile_task = None
        logger.info("BoostTracker initialized with database storage")

    async def cog_load(self):
        """Schedule a one-shot reconcile to catch boost changes that happened offline."""
        self._reconcile_task = asyncio.create_task(self._reconcile_on_ready())

    def cog_unload(self):
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()

    async def _reconcile_on_ready(self):
        """Sync the active-boosters collection with live Discord state after a restart.

        Boosts start/stop events only fire via on_member_update while the bot is online.
        On startup we diff guild.premium_subscribers against the DB and backfill the
        event log in both directions. No channel messages — silent catch-up only.
        """
        await self.bot.wait_until_ready()
        now = datetime.datetime.now(datetime.timezone.utc)

        for guild in self.bot.guilds:
            try:
                config = await get_config(guild.id)
                if not config.boost.get("enabled", False):
                    continue

                # premium_subscribers is derived from the member cache. If this
                # guild isn't fully chunked yet, the live set is incomplete and
                # the diff below would falsely "boost_end" every stored booster.
                # Force a chunk first; skip the guild if it can't be populated.
                if not guild.chunked:
                    try:
                        await guild.chunk()
                    except Exception as chunk_err:
                        logger.warning(
                            f"Skipping boost reconcile for guild {guild.id}: "
                            f"members not chunked ({chunk_err})"
                        )
                        continue

                boosts_collection = self.db_manager.get_collection_manager('serverdata_boosts')
                events_collection = self.db_manager.get_collection_manager('serverdata_boost_events')

                stored = await boosts_collection.find_many({'guild_id': guild.id})
                stored_by_id = {doc['user_id']: doc for doc in stored}
                live_ids = {m.id for m in guild.premium_subscribers}

                # Started boosting while offline → in Discord, missing from DB.
                for member in guild.premium_subscribers:
                    if member.id in stored_by_id:
                        continue
                    boost_start = member.premium_since or now
                    await boosts_collection.update_one(
                        {'guild_id': guild.id, 'user_id': member.id},
                        {'$set': {
                            'guild_id': guild.id,
                            'user_id': member.id,
                            'username': str(member),
                            'boost_start': boost_start,
                            'guild_name': str(guild.name),
                            'current_boosts': guild.premium_subscription_count,
                        }},
                        upsert=True,
                    )
                    await events_collection.create_one({
                        'guild_id': guild.id,
                        'user_id': member.id,
                        'username': str(member),
                        'event_type': 'boost_start',
                        'timestamp': member.premium_since or now,
                        'total_boosts': guild.premium_subscription_count,
                        'backfilled': True,
                    })
                    logger.info(f"Backfilled boost_start for {member} in {guild.name}")

                # Stopped boosting while offline → in DB, gone from Discord.
                for user_id, doc in stored_by_id.items():
                    if user_id in live_ids:
                        continue
                    start = doc.get('boost_start')
                    if isinstance(start, str):
                        start = datetime.datetime.fromisoformat(start)
                    duration = self._format_duration(now - start) if start else "Unknown"
                    await boosts_collection.delete_one({'guild_id': guild.id, 'user_id': user_id})
                    await events_collection.create_one({
                        'guild_id': guild.id,
                        'user_id': user_id,
                        'username': doc.get('username', str(user_id)),
                        'event_type': 'boost_end',
                        'timestamp': now,
                        'duration': duration,
                        'total_boosts': guild.premium_subscription_count,
                        'backfilled': True,
                    })
                    logger.info(f"Backfilled boost_end for user {user_id} in {guild.name}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Boost reconcile failed for guild {guild.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Track when members start or stop boosting."""
        # Cheap check first: this event fires on every nick/role/presence change.
        # Only touch config/DB when the boost state actually changed.
        if before.premium_since == after.premium_since:
            return

        config = await get_config(after.guild.id)
        if not config.boost.get("enabled", False):
            return

        if not before.premium_since and after.premium_since:
            await self.log_boost_start(after)
        elif before.premium_since and not after.premium_since:
            await self.log_boost_end(before)

    async def log_boost_start(self, member: discord.Member):
        """Log when a member starts boosting."""
        now = datetime.datetime.now(datetime.timezone.utc)
        guild_id = member.guild.id
        user_id = member.id
        # Discord's authoritative boost-start timestamp (survives bot restarts).
        boost_start = member.premium_since or now

        boost_doc = {
            'guild_id': guild_id,
            'user_id': user_id,
            'username': str(member),
            'boost_start': boost_start,
            'guild_name': str(member.guild.name),
            'current_boosts': member.guild.premium_subscription_count,
        }

        # Upsert in boosts collection (keyed by guild_id + user_id)
        try:
            boosts_collection = self.db_manager.get_collection_manager('serverdata_boosts')
            await boosts_collection.update_one(
                {'guild_id': guild_id, 'user_id': user_id},
                {'$set': boost_doc},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving boost start to DB: {e}", exc_info=True)

        # Log the event
        try:
            events_collection = self.db_manager.get_collection_manager('serverdata_boost_events')
            await events_collection.create_one({
                'guild_id': guild_id,
                'user_id': user_id,
                'username': str(member),
                'event_type': 'boost_start',
                'timestamp': now,
                'total_boosts': member.guild.premium_subscription_count
            })
        except Exception as e:
            logger.error(f"Error saving boost event to DB: {e}", exc_info=True)

        # Send to log channel
        await self.send_boost_log(
            member.guild,
            f"🚀 **Server Boosted**\n"
            f"**User:** {member.mention} (`{member}`)\n"
            f"**Action:** Started boosting the server!\n"
            f"**Total Boosts:** {member.guild.premium_subscription_count}\n"
            f"**Boost Level:** {self.get_boost_level(member.guild.premium_subscription_count)}\n"
            f"**Time:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

    async def log_boost_end(self, member: discord.Member):
        """Log when a member stops boosting."""
        now = datetime.datetime.now(datetime.timezone.utc)
        guild_id = member.guild.id
        user_id = member.id

        # Duration from Discord's own boost-start timestamp (no DB read needed).
        if member.premium_since:
            duration = self._format_duration(now - member.premium_since)
        else:
            duration = "Unknown"

        # Remove from active boosters
        try:
            boosts_collection = self.db_manager.get_collection_manager('serverdata_boosts')
            await boosts_collection.delete_one({'guild_id': guild_id, 'user_id': user_id})
        except Exception as e:
            logger.error(f"Error removing active booster from DB: {e}", exc_info=True)

        # Log the event
        try:
            events_collection = self.db_manager.get_collection_manager('serverdata_boost_events')
            await events_collection.create_one({
                'guild_id': guild_id,
                'user_id': user_id,
                'username': str(member),
                'event_type': 'boost_end',
                'timestamp': now,
                'duration': duration,
                'total_boosts': member.guild.premium_subscription_count
            })
        except Exception as e:
            logger.error(f"Error saving boost end event to DB: {e}", exc_info=True)

        # Send to log channel
        await self.send_boost_log(
            member.guild,
            f"😔 **Boost Removed**\n"
            f"**User:** {member.mention} (`{member}`)\n"
            f"**Action:** Stopped boosting the server\n"
            f"**Boost Duration:** {duration}\n"
            f"**Total Boosts:** {member.guild.premium_subscription_count}\n"
            f"**Boost Level:** {self.get_boost_level(member.guild.premium_subscription_count)}\n"
            f"**Time:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

    async def send_boost_log(self, guild: discord.Guild, message: str):
        """Send boost log to designated channel from guild config."""
        config = await get_config(guild.id)

        channel_id = config.boost.get("channel_id")
        if not channel_id:
            logger.debug(f"No boost log channel configured for guild {guild.name}, skipping log")
            return

        log_channel = self.bot.get_channel(channel_id)
        if not log_channel:
            logger.debug(f"Boost log channel {channel_id} not found in guild {guild.name}")
            return

        try:
            await log_channel.send(message)
        except discord.Forbidden:
            logger.warning(f"No permission to send messages in {log_channel.name}")

    @staticmethod
    def _format_duration(delta: datetime.timedelta) -> str:
        """Human-readable duration, dropping sub-second precision."""
        return str(delta).split('.')[0]

    def get_boost_level(self, boost_count: int) -> str:
        """Get the current boost level based on count."""
        if boost_count >= 14:
            return "Level 3 🚀"
        elif boost_count >= 7:
            return "Level 2 ⭐"
        elif boost_count >= 2:
            return "Level 1 ✨"
        else:
            return "No Level"

    @commands.command(name='boosters')
    async def list_boosters(self, ctx):
        """List all current server boosters (live from Discord)."""
        now = datetime.datetime.now(datetime.timezone.utc)

        # discord.py exposes the boosting members directly.
        boosters = sorted(
            ctx.guild.premium_subscribers,
            key=lambda m: m.premium_since or now,  # longest-boosting first
        )

        if not boosters:
            await ctx.send("No active boosters found.")
            return

        lines = []
        for member in boosters:
            if member.premium_since:
                dur = self._format_duration(now - member.premium_since)
            else:
                dur = "Unknown"
            lines.append(f"• {member.mention} — boosting for `{dur}`")

        # Embed description caps at 4096 chars; trim if a server has tons of boosts.
        description = ""
        shown = 0
        for line in lines:
            if len(description) + len(line) + 1 > 3900:
                break
            description += line + "\n"
            shown += 1
        if shown < len(lines):
            description += f"\n…and {len(lines) - shown} more."

        embed = discord.Embed(
            title=f"🚀 Current Server Boosters — {len(boosters)}",
            description=description,
            color=0xff73fa,
        )
        embed.set_footer(
            text=f"{ctx.guild.premium_subscription_count} boosts • "
                 f"{self.get_boost_level(ctx.guild.premium_subscription_count)}"
        )
        await ctx.send(embed=embed)

    @commands.command(name='boosthistory')
    async def boost_history(self, ctx, user: discord.Member = None):
        """Show a user's boost status and recent boost events."""
        target_user = user or ctx.author
        now = datetime.datetime.now(datetime.timezone.utc)

        embed = discord.Embed(
            title=f"Boost History — {target_user.display_name}",
            color=0xff73fa,
        )

        # Current status comes straight from the member object.
        if target_user.premium_since:
            duration = self._format_duration(now - target_user.premium_since)
            embed.add_field(name="Status", value="🚀 Currently boosting", inline=False)
            embed.add_field(
                name="Started",
                value=target_user.premium_since.strftime('%Y-%m-%d %H:%M:%S') + " UTC",
                inline=False,
            )
            embed.add_field(name="Duration", value=duration, inline=False)
        else:
            embed.add_field(name="Status", value="Not currently boosting", inline=False)

        # Past events from the event log (the real history).
        try:
            events_collection = self.db_manager.get_collection_manager('serverdata_boost_events')
            events = await events_collection.find_many(
                {'guild_id': ctx.guild.id, 'user_id': target_user.id},
                sort=[('timestamp', -1)],
                limit=5,
            )
        except Exception as e:
            logger.error(f"Error fetching boost history: {e}", exc_info=True)
            events = []

        if events:
            history_lines = []
            for ev in events:
                ts = ev.get('timestamp')
                if isinstance(ts, str):
                    ts = datetime.datetime.fromisoformat(ts)
                ts_str = ts.strftime('%Y-%m-%d %H:%M') if ts else "?"
                label = "Started boosting" if ev.get('event_type') == 'boost_start' else "Stopped boosting"
                extra = f" (lasted {ev['duration']})" if ev.get('duration') else ""
                history_lines.append(f"`{ts_str}` — {label}{extra}")
            embed.add_field(name="Recent Events", value="\n".join(history_lines), inline=False)

        if not target_user.premium_since and not events:
            await ctx.send(f"{target_user.mention} has no boost data available.")
            return

        await ctx.send(embed=embed)


async def setup(bot):
    """Required setup function for cog loading."""
    await bot.add_cog(BoostTracker(bot))
