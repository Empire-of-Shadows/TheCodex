import discord
from discord.ext import commands
import datetime
from typing import Dict, Any

from storage.database_manager import db_manager
from storage.config_manager import get_config
from utils.logger import get_logger

logger = get_logger("BoostTracker")


class BoostTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = db_manager
        logger.info("BoostTracker initialized with database storage")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Track when members start or stop boosting"""
        config = await get_config(after.guild.id)
        if not config.boost.get("enabled", False):
            return

        # Member started boosting
        if not before.premium_since and after.premium_since:
            await self.log_boost_start(after)

        # Member stopped boosting
        elif before.premium_since and not after.premium_since:
            await self.log_boost_end(before)

    async def log_boost_start(self, member: discord.Member):
        """Log when a member starts boosting"""
        now = datetime.datetime.now(datetime.timezone.utc)
        guild_id = member.guild.id
        user_id = member.id

        boost_doc = {
            'guild_id': guild_id,
            'user_id': user_id,
            'username': str(member),
            'boost_start': now,
            'guild_name': str(member.guild.name),
            'current_boosts': member.guild.premium_subscription_count
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
        """Log when a member stops boosting"""
        now = datetime.datetime.now(datetime.timezone.utc)
        guild_id = member.guild.id
        user_id = member.id

        # Get boost start time from DB
        duration = "Unknown"
        try:
            boosts_collection = self.db_manager.get_collection_manager('serverdata_boosts')
            boost_doc = await boosts_collection.find_one({'guild_id': guild_id, 'user_id': user_id})

            if boost_doc and 'boost_start' in boost_doc:
                start_time = boost_doc['boost_start']
                if isinstance(start_time, str):
                    start_time = datetime.datetime.fromisoformat(start_time)
                duration = str(now - start_time).split('.')[0]

            # Remove from active boosters
            await boosts_collection.delete_one({'guild_id': guild_id, 'user_id': user_id})
        except Exception as e:
            logger.error(f"Error handling boost end in DB: {e}", exc_info=True)

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
        """Send boost log to designated channel from guild config"""
        config = await get_config(guild.id)

        channel_id = config.boost["channel_id"]
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

    def get_boost_level(self, boost_count: int) -> str:
        """Get the current boost level based on count"""
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
        """List all current server boosters"""
        current_boosters = []

        # Get boost data from DB for this guild
        try:
            boosts_collection = self.db_manager.get_collection_manager('serverdata_boosts')
            boost_docs = await boosts_collection.find_many({'guild_id': ctx.guild.id})
            boost_lookup = {doc['user_id']: doc for doc in boost_docs}
        except Exception as e:
            logger.error(f"Error fetching boost data: {e}", exc_info=True)
            boost_lookup = {}

        for member in ctx.guild.members:
            if member.premium_since:
                boost_info = boost_lookup.get(member.id, {})
                start_time = boost_info.get('boost_start')

                if start_time:
                    if isinstance(start_time, str):
                        start_time = datetime.datetime.fromisoformat(start_time)
                    duration = datetime.datetime.now(datetime.timezone.utc) - start_time
                    duration_str = str(duration).split('.')[0]
                else:
                    duration_str = 'Unknown'

                current_boosters.append({
                    'member': member,
                    'duration': duration_str,
                })

        if not current_boosters:
            await ctx.send("No active boosters found.")
            return

        embed = discord.Embed(
            title=f"🚀 Current Server Boosters - {len(current_boosters)}",
            color=0xff73fa
        )

        for booster in current_boosters:
            embed.add_field(
                name=f"{booster['member'].display_name}",
                value=f"Boosting for: {booster['duration']}",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='boosthistory')
    async def boost_history(self, ctx, user: discord.Member = None):
        """Check boost history for a user (or yourself)"""
        target_user = user or ctx.author

        try:
            boosts_collection = self.db_manager.get_collection_manager('serverdata_boosts')
            user_data = await boosts_collection.find_one({
                'guild_id': ctx.guild.id,
                'user_id': target_user.id
            })
        except Exception as e:
            logger.error(f"Error fetching boost history: {e}", exc_info=True)
            user_data = None

        if user_data and 'boost_start' in user_data:
            start_time = user_data['boost_start']
            if isinstance(start_time, str):
                start_time = datetime.datetime.fromisoformat(start_time)
            duration = datetime.datetime.now(datetime.timezone.utc) - start_time

            embed = discord.Embed(
                title=f"Boost History - {target_user.display_name}",
                color=0x00ff00
            )
            embed.add_field(name="Started Boosting", value=start_time.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
            embed.add_field(name="Duration", value=str(duration).split('.')[0], inline=False)
            embed.add_field(name="Total Server Boosts", value=ctx.guild.premium_subscription_count, inline=False)

            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{target_user.mention} is not currently boosting or no data available.")


async def setup(bot):
    """Required setup function for cog loading"""
    await bot.add_cog(BoostTracker(bot))
