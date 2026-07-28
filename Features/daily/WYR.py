import asyncio
import random
import logging
import os
from datetime import datetime, timedelta, timezone
import pytz
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

from Features.daily import wyr_notify
from startup.bot import s
from storage.log import get_logger, PerformanceLogger
from storage.settings.collections import db_manager
from storage.settings.config_manager import get_config, get_guild_config_manager
from admin.setup_notice import send_setup_notice

# Load environment variables
load_dotenv()

# Constants
OPTION1_EMOJI = "1️⃣"  # Reaction for option 1
OPTION2_EMOJI = "2️⃣"  # Reaction for option 2
OPTION3_EMOJI = "3️⃣"  # Reaction for option 3

logger = get_logger("WYR")


def _channel_allows_nsfw(channel) -> bool:
    """Whether NSFW questions may be posted in this channel.

    Only Discord's own age-restriction flag counts. Threads inherit the flag
    from their parent channel. Anything that cannot answer the question (DMs,
    a partially-resolved channel) is treated as not age-restricted.
    """
    try:
        return bool(channel.is_nsfw())
    except AttributeError:
        return False


def _format_wyr_string(template: str, question: dict, now: "datetime") -> str:
    """Substitute supported placeholders in a WYR thread format string."""
    tags = question.get("tags") or []
    category = tags[0].title() if tags else "General"
    return (
        template
        .replace("{date}",         now.strftime("%m/%d"))
        .replace("{question_num}", str(question.get("id", "")))
        .replace("{category}",     category)
        .replace("{option_1}",     question.get("option_1", ""))
        .replace("{option_2}",     question.get("option_2", ""))
        .replace("{option_3}",     question.get("option_3") or "")
        .replace("{question}",     question.get("original", ""))
    )


class WYRCommandGroup(app_commands.Group):
    """Command group for Would You Rather commands"""

    def __init__(self, cog):
        # guild_only: every WYR command scopes its queries by guild_id, so a DM
        # invocation would run a None-keyed lookup. Marking the group guild-only
        # registers all its commands DM-unavailable.
        super().__init__(name="wyr", description="Would You Rather commands", guild_only=True)
        self.cog = cog

    @app_commands.command(name="post", description="Manually post a WYR question (Admin only)")
    @app_commands.describe(
        category="Category of question (sfw, nsfw, mixed)",
        random_pick="Pick a random question instead of least used"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def post_wyr(self, interaction: discord.Interaction, category: str = None, random_pick: bool = False):
        """
        Manually post a WYR question.
        """
        logger.info(
            f"Manual WYR post requested by {interaction.user} (ID: {interaction.user.id}) - Category: {category}, Random: {random_pick}")

        try:
            with PerformanceLogger(logger, f"post_wyr_command_{category}"):
                # Read guild settings from config
                guild_id = interaction.guild_id
                guild_config = await get_config(guild_id)

                if category is None:
                    category = guild_config.wyr.get("default_category", "sfw")

                # NSFW questions only go to age-restricted channels. An explicit
                # NSFW request is refused outright rather than quietly answered
                # with an SFW question, so the admin knows why.
                allow_nsfw = _channel_allows_nsfw(interaction.channel)
                if category == "nsfw" and not allow_nsfw:
                    logger.warning(
                        f"Blocked NSFW WYR post by {interaction.user} in non-age-restricted "
                        f"channel {interaction.channel_id}"
                    )
                    await interaction.response.send_message(
                        "❌ NSFW questions can only be posted in age-restricted channels. "
                        "Enable **Age-Restricted Channel** in this channel's settings, or pick "
                        "the `sfw` category.",
                        ephemeral=True,
                    )
                    return

                if random_pick:
                    question = await self.cog.get_random_question(category, guild_id=guild_id, allow_nsfw=allow_nsfw)
                else:
                    question = await self.cog.get_next_question(category, guild_id=guild_id, allow_nsfw=allow_nsfw)

                if not question:
                    logger.warning(f"No {category} questions available for manual post by {interaction.user}")
                    await interaction.response.send_message(f"There are no {category} questions available right now.",
                                                            ephemeral=True)
                    return

                embed = self.cog.create_question_embed(question)
                has_option3 = bool(question.get("option_3"))
                view = WYRView(question["_id"], self.cog, has_option3=has_option3)

                await interaction.response.send_message(embed=embed, view=view)
                message = await interaction.original_response()

                # Store the message-question mapping with guild info
                await self.cog.store_message_question_mapping(
                    message.id,
                    question["_id"],
                    channel_id=interaction.channel_id,
                    guild_id=guild_id
                )

                # Read thread settings from guild config
                thread_name_fmt = guild_config.wyr.get("thread_name_format", "🎲 WYR · Q{question_num} · {date}")
                archive_dur = guild_config.wyr.get("thread_auto_archive", 1440)
                starter_msg = guild_config.wyr.get("thread_starter_message", "🎲 **{question}**")
                tz_name = guild_config.wyr.get("timezone", "America/Chicago")
                tz = pytz.timezone(tz_name)
                now = datetime.now(tz)

                thread_name = _format_wyr_string(thread_name_fmt, question, now)[:100]
                thread = await message.create_thread(
                    name=thread_name,
                    auto_archive_duration=archive_dur
                )

                await thread.send(_format_wyr_string(starter_msg, question, now))

                logger.info(f"Successfully posted manual WYR question {question['_id']} in thread {thread.id}")

        except Exception as e:
            logger.error(f"Error in manual WYR post by {interaction.user}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred while posting the question.",
                                                        ephemeral=True)

    @app_commands.command(name="stats", description="Check WYR voting statistics for yourself or another user")
    @app_commands.describe(user="User to check stats for (defaults to yourself)")
    async def wyr_stats(self, interaction: discord.Interaction, user: discord.Member = None):
        """
        Check WYR voting statistics for yourself or another user.
        """
        target_user = user or interaction.user
        logger.info(f"WYR stats requested by {interaction.user} for user {target_user} (ID: {target_user.id})")

        try:
            with PerformanceLogger(logger, f"wyr_stats_lookup_{target_user.id}"):
                stats = await self.cog.get_user_stats(target_user.id, interaction.guild_id)

                embed = discord.Embed(
                    title=f" WYR Stats for {target_user.display_name}",
                    color=discord.Color.green()
                )

                embed.add_field(
                    name=f"{OPTION1_EMOJI} Option 1 Votes",
                    value=f"{stats['option1_votes']:,}",
                    inline=True
                )
                embed.add_field(
                    name=f"{OPTION2_EMOJI} Option 2 Votes",
                    value=f"{stats['option2_votes']:,}",
                    inline=True
                )
                if stats['option3_votes'] > 0:
                    embed.add_field(
                        name=f"{OPTION3_EMOJI} Option 3 Votes",
                        value=f"{stats['option3_votes']:,}",
                        inline=True
                    )
                embed.add_field(
                    name="️ Total Votes",
                    value=f"{stats['total_votes']:,}",
                    inline=True
                )

                if stats['total_votes'] > 0:
                    option1_pct = (stats['option1_votes'] / stats['total_votes']) * 100
                    option2_pct = (stats['option2_votes'] / stats['total_votes']) * 100
                    pref_text = f"Option 1: {option1_pct:.1f}%\nOption 2: {option2_pct:.1f}%"
                    if stats['option3_votes'] > 0:
                        option3_pct = (stats['option3_votes'] / stats['total_votes']) * 100
                        pref_text += f"\nOption 3: {option3_pct:.1f}%"
                    embed.add_field(
                        name=" Voting Preference",
                        value=pref_text,
                        inline=False
                    )

                # Add timestamps if available
                if stats.get('first_vote'):
                    embed.add_field(
                        name=" First Vote",
                        value=f"<t:{int(stats['first_vote'].timestamp())}:R>",
                        inline=True
                    )
                if stats.get('last_vote'):
                    embed.add_field(
                        name=" Last Vote",
                        value=f"<t:{int(stats['last_vote'].timestamp())}:R>",
                        inline=True
                    )

                embed.set_thumbnail(url=target_user.display_avatar.url)
                await interaction.response.send_message(embed=embed)

                logger.info(f"WYR stats successfully displayed for {target_user} (Total votes: {stats['total_votes']})")

        except Exception as e:
            logger.error(f"Error retrieving WYR stats for {target_user}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while fetching stats.", ephemeral=True)

    @app_commands.command(name="notify", description="Get pinged (or stop being pinged) when a new WYR question is posted")
    async def wyr_notify_command(self, interaction: discord.Interaction):
        """Show the member's notification state with the one button that changes it."""
        logger.info(f"WYR notify settings opened by {interaction.user} (ID: {interaction.user.id})")

        try:
            content, view = await wyr_notify.build_status_view(interaction.user)
            # No view when notifications are unavailable; send_message rejects a None one.
            extra = {"view": view} if view is not None else {}
            await interaction.response.send_message(content=content, ephemeral=True, **extra)
        except Exception as e:
            logger.error(f"Error opening WYR notify settings for {interaction.user}: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while checking your notification settings.", ephemeral=True
            )

    @app_commands.command(name="results", description="Show results for a specific WYR question")
    @app_commands.describe(message_id="Message ID of the WYR question to check results for")
    async def wyr_results(self, interaction: discord.Interaction, message_id: str = None):
        """
        Show results for a specific WYR question.
        """
        logger.info(f"WYR results requested by {interaction.user} for message ID: {message_id}")

        if not message_id:
            logger.warning(f"WYR results request missing message ID from {interaction.user}")
            await interaction.response.send_message(
                "Please provide the message ID of the WYR question you want to check results for.", ephemeral=True)
            return

        try:
            # Get question ID from mapping
            question_id = await self.cog.get_question_id_from_message(int(message_id))
            if not question_id:
                logger.warning(f"No question mapping found for message ID {message_id} by {interaction.user}")
                await interaction.response.send_message(
                    "No WYR question found for that message ID. It might be from an older post.", ephemeral=True)
                return

            # Get results using the question ID
            results = await self.cog.get_question_results(question_id, interaction.guild_id)
            if not results:
                logger.warning(f"Could not fetch results for question {question_id} from message {message_id}")
                await interaction.response.send_message("❌ Could not fetch results for that question.", ephemeral=True)
                return

            # Create results embed
            embed = discord.Embed(
                title="📊 WYR Results",
                color=discord.Color.green()
            )

            # Create visual progress bars
            def create_bar(percentage, length=20):
                filled = int(percentage / 100 * length)
                return "█" * filled + "░" * (length - filled)

            bar1 = create_bar(results['option1_percentage'])
            bar2 = create_bar(results['option2_percentage'])

            embed.add_field(
                name=f"{OPTION1_EMOJI} Option 1",
                value=f"{bar1} {results['option1_percentage']:.1f}% ({results['option1_votes']} votes)",
                inline=False
            )
            embed.add_field(
                name=f"{OPTION2_EMOJI} Option 2",
                value=f"{bar2} {results['option2_percentage']:.1f}% ({results['option2_votes']} votes)",
                inline=False
            )

            if results.get('option3_votes') is not None:
                bar3 = create_bar(results['option3_percentage'])
                embed.add_field(
                    name=f"{OPTION3_EMOJI} Option 3",
                    value=f"{bar3} {results['option3_percentage']:.1f}% ({results['option3_votes']} votes)",
                    inline=False
                )

            embed.add_field(
                name=" Total Votes",
                value=f"{results['total_votes']} people have voted",
                inline=False
            )

            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully showed results for question {question_id} via command")

        except (ValueError, discord.NotFound):
            logger.warning(f"Invalid or not found message ID {message_id} requested by {interaction.user}")
            await interaction.response.send_message("Invalid message ID or message not found.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error fetching WYR results for message {message_id}: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while fetching results.", ephemeral=True)

    @app_commands.command(name="leaderboard", description="Show the WYR voting leaderboard")
    @app_commands.describe(limit="Number of users to show in leaderboard (default: 10)")
    async def wyr_leaderboard(self, interaction: discord.Interaction,
                              limit: app_commands.Range[int, 1, 25] = 10):
        """
        Show the WYR voting leaderboard using the dedicated leaderboard collection.
        """
        logger.info(f"WYR leaderboard requested by {interaction.user} with limit: {limit}")

        try:
            with PerformanceLogger(logger, f"wyr_leaderboard_generation_limit_{limit}"):
                # Get top users from leaderboard collection - filtered to current guild
                top_users = await db_manager.daily_wyr_leaderboard.find_many(
                    filter_dict={"guild_id": str(interaction.guild_id)},
                    sort=[("total_votes", -1)],
                    limit=limit
                )

                if not top_users:
                    logger.info("No WYR voting data available for leaderboard")
                    # No votes on a server with no WYR channel means questions were
                    # never switched on, so point at setup instead of implying
                    # nobody has voted.
                    guild_config = await get_config(interaction.guild_id)
                    if not guild_config.wyr.get("channel_id"):
                        await send_setup_notice(
                            interaction,
                            what="Would You Rather",
                            path="WYR Settings -> WYR Channel",
                            detail="No questions have been posted, so there is nothing to rank yet.",
                        )
                        return
                    await interaction.response.send_message("No voting data available yet!")
                    return

                embed = discord.Embed(
                    title=" WYR Voting Leaderboard",
                    description="Most active voters in Would You Rather questions",
                    color=discord.Color.gold()
                )

                leaderboard_text = ""
                for i, user_data in enumerate(top_users, 1):
                    try:
                        user = await self.cog.bot.fetch_user(int(user_data["user_id"]))
                        emoji = "" if i == 1 else "" if i == 2 else "" if i == 3 else ""
                        vote_count = user_data["total_votes"]
                        leaderboard_text += f"{emoji} **{i}.** {user.mention} - {vote_count:,} votes\n"
                    except Exception:
                        vote_count = user_data["total_votes"]
                        leaderboard_text += f" **{i}.** Unknown User - {vote_count:,} votes\n"
                        logger.warning(f"Could not fetch user data for user ID {user_data.get('user_id')}")

                embed.description = leaderboard_text
                embed.set_footer(text=f"Showing top {min(limit, len(top_users))} voters")

                await interaction.response.send_message(embed=embed)
                logger.info(f"WYR leaderboard successfully generated with {len(top_users)} users")

        except Exception as e:
            logger.error(f"Error generating WYR leaderboard: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while generating the leaderboard.",
                                                    ephemeral=True)

    @app_commands.command(name="reset_stats", description="Reset a user's WYR statistics (Admin only)")
    @app_commands.describe(user="User to reset stats for")
    @app_commands.default_permissions(administrator=True)
    async def wyr_reset_stats(self, interaction: discord.Interaction, user: discord.Member):
        """
        Reset a user's WYR statistics (Admin only).
        """
        logger.warning(f"WYR stats reset requested by {interaction.user} for {user} (ID: {user.id})")

        try:
            with PerformanceLogger(logger, f"wyr_stats_reset_{user.id}"):
                # Delete this user's stats for the current guild only
                success = await db_manager.daily_wyr_leaderboard.delete_one(
                    {"user_id": str(user.id), "guild_id": str(interaction.guild_id)}
                )

                if success:
                    embed = discord.Embed(
                        title="✅ Stats Reset",
                        description=f"Successfully reset WYR statistics for {user.mention}",
                        color=discord.Color.green()
                    )
                    logger.info(f"Successfully reset WYR stats for {user} (ID: {user.id})")
                else:
                    embed = discord.Embed(
                        title="ℹ️ No Stats Found",
                        description=f"No WYR statistics found for {user.mention}",
                        color=discord.Color.blue()
                    )
                    logger.info(f"No WYR stats found to reset for {user} (ID: {user.id})")

                await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error resetting WYR stats for {user}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while resetting stats.", ephemeral=True)


class WYR(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._posted_today: set = set()
        self._last_cleanup_date: str = ""
        # Track startup tasks so cog_unload can cancel them (they wait_until_ready and
        # would otherwise linger past an unload/reload).
        self._bg_tasks = [
            self.bot.loop.create_task(self.initialize_database()),
            self.bot.loop.create_task(self._register_views()),
        ]
        # Add the command group to the bot
        self.wyr_commands = WYRCommandGroup(self)
        self.bot.tree.add_command(self.wyr_commands)

        logger.info("WYR cog initialized - starting database initialization")

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        logger.info("WYR cog unloading - cleaning up")

        for task in getattr(self, "_bg_tasks", []):
            task.cancel()

        if self.wyr_tick.is_running():
            self.wyr_tick.cancel()
        self.bot.tree.remove_command("wyr")
        logger.info("WYR command group removed from bot tree")

    async def _register_views(self):
        """Register persistent views after bot is ready"""
        await self.bot.wait_until_ready()
        # Register the view without question_id and cog - they will be set when needed
        self.bot.add_view(WYRView(has_option3=True))
        logger.info("Persistent WYRView registered after bot ready")

    async def initialize_database(self):
        """
        Initialize the database connection using the new DatabaseManager.
        """
        try:
            with PerformanceLogger(logger, "wyr_database_initialization"):
                # Initialize the global database manager if not already initialized
                if not db_manager._initialized:
                    await db_manager.initialize()

                logger.info(f"{s}✅ WYR database initialized successfully")

                # Start the per-guild tick loop
                if not self.wyr_tick.is_running():
                    self.wyr_tick.start()
                    logger.info("WYR tick loop started")

        except Exception as e:
            logger.error(f"{s}❌ Failed to initialize WYR database: {e}", exc_info=True)

    async def store_message_question_mapping(self, message_id, question_id, channel_id=None, guild_id=None):
        """
        Store the relationship between message ID and question ID in the database.
        """
        try:
            with PerformanceLogger(logger, f"store_mapping_{message_id}"):
                # Snowflake IDs are stored as strings; question_id is an internal
                # question number, not a snowflake, and stays an int.
                mapping_data = {
                    "message_id": str(message_id),
                    "question_id": question_id,
                    "created_at": datetime.now(timezone.utc),
                    "channel_id": str(channel_id) if channel_id is not None else None,
                    "guild_id": str(guild_id) if guild_id is not None else None
                }

                # Use the new database manager to create the mapping
                await db_manager.daily_wyr_mappings.create_one(mapping_data)
                logger.info(f"Stored message-question mapping: message {message_id} -> question {question_id}")

        except Exception as e:
            logger.error(f"Error storing message-question mapping for message {message_id}: {e}", exc_info=True)

    async def get_question_id_from_message(self, message_id):
        """
        Get question ID from message ID using the stored mapping.
        """
        try:
            with PerformanceLogger(logger, f"get_question_id_{message_id}"):
                # Use the new database manager to find the mapping
                mapping = await db_manager.daily_wyr_mappings.find_one({"message_id": str(message_id)})

                if mapping:
                    question_id = mapping.get("question_id")
                    logger.info(f"Retrieved question ID {question_id} for message {message_id}")
                    return question_id
                else:
                    logger.warning(f"No mapping found for message ID {message_id}")
                    return None

        except Exception as e:
            logger.error(f"Error retrieving question ID for message {message_id}: {e}", exc_info=True)
            return None

    async def get_message_id_from_question(self, question_id):
        """
        Get message ID from question ID using the stored mapping.
        """
        try:
            with PerformanceLogger(logger, f"get_message_id_{question_id}"):
                # Use the new database manager to find the mapping
                mapping = await db_manager.daily_wyr_mappings.find_one({"question_id": question_id})

                if mapping:
                    message_id = mapping.get("message_id")
                    logger.info(f"Retrieved message ID {message_id} for question {question_id}")
                    return int(message_id) if message_id else None
                else:
                    logger.warning(f"No mapping found for question ID {question_id}")
                    return None

        except Exception as e:
            logger.error(f"Error retrieving message ID for question {question_id}: {e}", exc_info=True)
            return None

    async def cleanup_old_mappings(self):
        """
        Clean up old message-question mappings per-guild using each guild's
        configured mapping_cleanup_days setting.
        """
        try:
            with PerformanceLogger(logger, "cleanup_old_mappings"):
                config_mgr = await get_guild_config_manager()
                guilds = await config_mgr.get_all_configured_guilds()
                total_deleted = 0

                for guild_id in guilds:
                    try:
                        guild_config = await config_mgr.get_config(guild_id)
                        days_old = guild_config.wyr.get("mapping_cleanup_days", 30)
                        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

                        result = await db_manager.daily_wyr_mappings.delete_many({
                            "guild_id": str(guild_id),
                            "created_at": {"$lt": cutoff_date},
                        })
                        total_deleted += result or 0
                    except Exception as e:
                        logger.error(f"Error cleaning mappings for guild {guild_id}: {e}", exc_info=True)

                if total_deleted:
                    logger.info(f"Cleaned up {total_deleted} old message-question mappings")

        except Exception as e:
            logger.error(f"Error cleaning up old mappings: {e}", exc_info=True)

    async def get_last_post_time(self, guild_id):
        """Get the timestamp of the most recent scheduled post for a guild from the database."""
        try:
            mappings = await db_manager.daily_wyr_mappings.find_many(
                filter_dict={"guild_id": str(guild_id)},
                sort=[("created_at", -1)],
                limit=1
            )
            if mappings:
                return mappings[0].get("created_at")
            return None
        except Exception as e:
            logger.error(f"Error getting last post time for guild {guild_id}: {e}", exc_info=True)
            return None

    # Posts for guilds that are due in the same tick run concurrently (bounded),
    # so 200 servers sharing a 12:00 slot don't serialize into a multi-minute
    # backlog that pushes the next tick past its window.
    _POST_CONCURRENCY = 10

    @tasks.loop(minutes=1)
    async def wyr_tick(self):
        """Every minute, post for any guild that is due, with bounded concurrency."""
        try:
            config_mgr = await get_guild_config_manager()
            guilds = await config_mgr.get_all_configured_guilds()

            # Clean stale entries from _posted_today (keep only today's entries)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self._posted_today = {
                key for key in self._posted_today
                if key[1] >= today_str  # keep today and future (across timezones)
            }

            # Run mapping cleanup once per UTC day
            if today_str != self._last_cleanup_date:
                self._last_cleanup_date = today_str
                await self.cleanup_old_mappings()

            # Phase 1 - figure out which guilds are due. Cheap (config + one DB
            # read each) and sequential so the schedule bookkeeping stays simple.
            due: list[tuple] = []
            for guild_id in guilds:
                try:
                    decision = await self._evaluate_guild_due(guild_id, config_mgr)
                    if decision is not None:
                        due.append(decision)
                except Exception as guild_error:
                    logger.error(f"Error checking WYR schedule for guild {guild_id}: {guild_error}", exc_info=True)

            if not due:
                return

            # Phase 2 - post concurrently with a cap. Mark a guild as posted only
            # on success so transient failures retry next tick.
            sem = asyncio.Semaphore(self._POST_CONCURRENCY)

            async def _run(guild_id, guild_config, today_key):
                async with sem:
                    try:
                        posted = await self.post_daily_question_for_guild(guild_id, guild_config)
                    except Exception as e:
                        logger.error(f"Error posting WYR to guild {guild_id}: {e}", exc_info=True)
                        posted = False
                    if posted:
                        self._posted_today.add(today_key)

            await asyncio.gather(*(_run(*d) for d in due))

        except Exception as e:
            logger.error(f"Error in WYR tick loop: {e}", exc_info=True)

    async def _evaluate_guild_due(self, guild_id, config_mgr):
        """Decide whether a guild should post now.

        Returns (guild_id, guild_config, today_key) if it is due, else None.
        Guilds already handled today (in-memory or per the DB) and the
        skip-initial-post case are recorded in `_posted_today` here so they are
        not reconsidered, but they never enter the posting phase.
        """
        guild_config = await config_mgr.get_config(guild_id)
        if not guild_config.wyr.get("enabled", False) or not guild_config.wyr["channel_id"]:
            return None

        hour = guild_config.wyr["post_hour"]
        minute = guild_config.wyr["post_minute"]
        tz_name = guild_config.wyr["timezone"]
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)

        today_key = (guild_id, now.strftime("%Y-%m-%d"))

        # Fast in-memory check - already handled this guild today
        if today_key in self._posted_today:
            return None

        scheduled_now = now.hour == hour and now.minute == minute
        scheduled_passed = (now.hour > hour) or (now.hour == hour and now.minute >= minute)

        if not (scheduled_now or scheduled_passed):
            return None

        # Check DB for the last post time - skip if already posted today
        last_post = await self.get_last_post_time(guild_id)

        if last_post:
            if last_post.tzinfo is None:
                last_post = last_post.replace(tzinfo=timezone.utc)
            last_post_local = last_post.astimezone(tz)
            if last_post_local.date() == now.date():
                self._posted_today.add(today_key)
                logger.info(
                    f"Skipping WYR for guild {guild_id}: already posted today "
                    f"({last_post_local.strftime('%Y-%m-%d %H:%M')} {tz_name})"
                )
                return None

        # First-time setup: allow admin to skip the initial catch-up post
        if not last_post and guild_config.wyr.get("skip_initial_post", False):
            self._posted_today.add(today_key)
            guild_config.wyr["skip_initial_post"] = False
            await config_mgr.save_config(guild_config)
            logger.info(f"Skipping initial WYR post for guild {guild_id} (skip_initial_post flag)")
            return None

        if scheduled_now:
            logger.info(f"Posting scheduled WYR for guild {guild_id} at {hour:02d}:{minute:02d}")
        else:
            logger.info(
                f"Catch-up WYR post for guild {guild_id} "
                f"(scheduled {hour:02d}:{minute:02d}, now {now.strftime('%H:%M')})"
            )

        return (guild_id, guild_config, today_key)

    @wyr_tick.before_loop
    async def before_wyr_tick(self):
        """Wait until bot is ready before starting tick loop."""
        await self.bot.wait_until_ready()

    async def post_daily_question_for_guild(self, guild_id, guild_config) -> bool:
        """
        Post a daily WYR question for a single guild using per-guild settings.

        Returns True only if the question was actually posted. The caller marks
        the guild as "posted today" solely on a True result, so a transient
        failure (permissions blip, 5xx) is retried on the next tick instead of
        silently skipping the guild for the whole day.
        """
        if not guild_config.wyr.get("enabled", False):
            return False

        logger.info(f"Posting scheduled WYR question for guild {guild_id}")

        try:
            with PerformanceLogger(logger, f"wyr_post_guild_{guild_id}"):
                channel = self.bot.get_channel(guild_config.wyr["channel_id"])
                if not channel:
                    logger.warning(f"WYR channel {guild_config.wyr['channel_id']} not found for guild {guild_id}")
                    return False

                category = guild_config.wyr.get("default_category", "sfw")

                # The daily post is unattended, so an NSFW-only category aimed at
                # a channel that is not age-restricted falls back to SFW rather
                # than skipping the day entirely. A "mixed" category needs no
                # special case - the fetch narrows it to SFW on its own.
                allow_nsfw = _channel_allows_nsfw(channel)
                if category == "nsfw" and not allow_nsfw:
                    logger.warning(
                        f"Guild {guild_id} has WYR category 'nsfw' but channel "
                        f"{channel.id} is not age-restricted - posting an SFW question instead"
                    )
                    category = "sfw"

                question = await self.get_next_question(category, guild_id=guild_id, allow_nsfw=allow_nsfw)
                if not question:
                    logger.warning(f"No {category} questions available for guild {guild_id} - skipping")
                    return False

                embed = self.create_question_embed(question)
                has_option3 = bool(question.get("option_3"))
                view = WYRView(question["_id"], self, has_option3=has_option3)

                # Build ping content if role is configured
                ping_content = f"<@&{guild_config.wyr['ping_role_id']}>" if guild_config.wyr.get("ping_role_id") else None
                # Explicit override: the bot's global default suppresses role pings,
                # but the configured WYR ping role is an intentional ping.
                message = await channel.send(
                    content=ping_content,
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )

                # Store the message-question mapping with guild info
                await self.store_message_question_mapping(
                    message.id,
                    question["_id"],
                    channel_id=guild_config.wyr["channel_id"],
                    guild_id=guild_id
                )

                # Read thread settings from guild config
                thread_name_fmt = guild_config.wyr.get("thread_name_format", "🎲 WYR · Q{question_num} · {date}")
                archive_dur = guild_config.wyr.get("thread_auto_archive", 1440)
                starter_msg = guild_config.wyr.get("thread_starter_message", "🎲 **{question}**")
                tz_name = guild_config.wyr.get("timezone", "America/Chicago")
                tz = pytz.timezone(tz_name)
                now = datetime.now(tz)

                thread_name = _format_wyr_string(thread_name_fmt, question, now)[:100]
                thread = await message.create_thread(
                    name=thread_name,
                    auto_archive_duration=archive_dur
                )

                await thread.send(_format_wyr_string(starter_msg, question, now))

                await self.increment_used_count(question["_id"], guild_id)
                logger.info(f"Posted WYR question {question['_id']} in guild {guild_id}, channel {guild_config.wyr['channel_id']}")
                return True

        except Exception as e:
            logger.error(f"Error posting WYR to guild {guild_id}: {e}", exc_info=True)
            return False

    async def update_user_leaderboard(self, user_id, guild_id, option_chosen):
        """
        Update user statistics in the WYR_Leaderboard collection (per-guild scoped).
        """
        try:
            with PerformanceLogger(logger, f"update_user_leaderboard_{user_id}_{guild_id}"):
                user_id_str = str(user_id)
                gid_str = str(guild_id)
                now = datetime.now(timezone.utc)

                user_stats = await db_manager.daily_wyr_leaderboard.find_one(
                    {"user_id": user_id_str, "guild_id": gid_str}
                )

                if not user_stats:
                    new_user = {
                        "user_id": user_id_str,
                        "guild_id": gid_str,
                        "total_votes": 1,
                        "option1_votes": 1 if option_chosen == "option1" else 0,
                        "option2_votes": 1 if option_chosen == "option2" else 0,
                        "option3_votes": 1 if option_chosen == "option3" else 0,
                        "score": 1,
                        "first_vote": now,
                        "last_vote": now,
                        "updated_at": now,
                    }
                    await db_manager.daily_wyr_leaderboard.create_one(new_user)
                    logger.info(f"Created leaderboard entry for user {user_id} in guild {guild_id}: {option_chosen}")
                else:
                    new_total = user_stats.get("total_votes", 0) + 1
                    update_query = {
                        "$inc": {
                            "total_votes": 1,
                            f"{option_chosen}_votes": 1,
                        },
                        "$set": {
                            "last_vote": now,
                            "updated_at": now,
                            "score": new_total,
                        },
                    }
                    await db_manager.daily_wyr_leaderboard.update_one(
                        {"user_id": user_id_str, "guild_id": gid_str},
                        update_query,
                    )
                    logger.info(
                        f"Updated leaderboard for user {user_id} in guild {guild_id}: {option_chosen} (total: {new_total})"
                    )

        except Exception as e:
            logger.error(f"Error updating user leaderboard for {user_id} in guild {guild_id}: {e}", exc_info=True)

    @staticmethod
    def _build_category_query(category: str, allow_nsfw: bool) -> dict | None:
        """Build the question filter for a category.

        `allow_nsfw` reflects the destination channel's age restriction and is
        the last word: unless it is True the filter always pins `nsfw: False`,
        so no category (including tag categories, which can name anything) can
        pull an NSFW question into a channel that is not age-restricted.
        Returns None when the category itself is NSFW-only and NSFW is not
        allowed, since there is no safe question to serve.
        """
        if category == "sfw":
            query = {"nsfw": False}
        elif category == "nsfw":
            if not allow_nsfw:
                return None
            query = {"nsfw": True}
        elif category == "mixed":
            query = {}
        else:
            query = {"tags": category}

        if not allow_nsfw:
            query["nsfw"] = False
        return query

    async def get_next_question(self, category="sfw", guild_id=None, exclude_used=False, allow_nsfw=False):
        """
        Fetch the next "Would You Rather" question for a guild - least-used in that guild first.
        """
        try:
            with PerformanceLogger(logger, f"get_next_question_{category}_{guild_id}"):
                query = self._build_category_query(category, allow_nsfw)
                if query is None:
                    logger.warning(
                        f"Refusing to serve an NSFW question for guild {guild_id}: "
                        f"category is {category} but the channel is not age-restricted"
                    )
                    return None

                gid_str = str(guild_id) if guild_id is not None else None
                used_path = f"guilds.{gid_str}.used_count" if gid_str else "used_count"

                if exclude_used:
                    # Treat missing nested key (never posted in this guild) as zero.
                    query["$or"] = [
                        {used_path: {"$exists": False}},
                        {used_path: 0},
                    ]

                questions = await db_manager.daily_wyr.find_many(
                    filter_dict=query,
                    sort=[(used_path, 1)],
                    limit=1,
                )

                if questions:
                    question = questions[0]
                    used = ((question.get("guilds") or {}).get(gid_str) or {}).get("used_count", 0) if gid_str else question.get("used_count", 0)
                    logger.info(
                        f"Retrieved next {category} question: ID {question['_id']} (guild_used_count: {used})"
                    )
                    return question
                else:
                    logger.warning(f"No {category} questions available for guild {guild_id} (exclude_used: {exclude_used})")
                    return None

        except Exception as e:
            logger.error(f"Error fetching next WYR question ({category}, guild {guild_id}): {e}", exc_info=True)
            return None

    async def get_random_question(self, category="sfw", guild_id=None, allow_nsfw=False):
        """
        Get a random question from the specified category using the new DatabaseManager.
        """
        try:
            with PerformanceLogger(logger, f"get_random_question_{category}"):
                match_filter = self._build_category_query(category, allow_nsfw)
                if match_filter is None:
                    logger.warning(
                        f"Refusing to serve a random NSFW question for guild {guild_id}: "
                        f"category is {category} but the channel is not age-restricted"
                    )
                    return None

                pipeline = [
                    {"$match": match_filter},
                    {"$sample": {"size": 1}}
                ]

                # Use the new database manager for aggregation
                questions = await db_manager.daily_wyr.aggregate(pipeline)

                if questions:
                    question = questions[0]
                    logger.info(f"Retrieved random {category} question: ID {question['_id']}")
                    return question
                else:
                    logger.warning(f"No {category} questions available for random selection")
                    return None

        except Exception as e:
            logger.error(f"Error fetching random WYR question ({category}): {e}", exc_info=True)
            return None

    async def get_user_stats(self, user_id, guild_id):
        """
        Get user voting statistics for a specific guild from the leaderboard collection.
        """
        default_stats = {"option1_votes": 0, "option2_votes": 0, "option3_votes": 0, "total_votes": 0}

        try:
            with PerformanceLogger(logger, f"get_user_stats_{user_id}_{guild_id}"):
                user_stats = await db_manager.daily_wyr_leaderboard.find_one(
                    {"user_id": str(user_id), "guild_id": str(guild_id)}
                )

                if not user_stats:
                    logger.info(f"No stats found for user {user_id} in guild {guild_id}")
                    return default_stats

                stats = {
                    "option1_votes": user_stats.get("option1_votes", 0),
                    "option2_votes": user_stats.get("option2_votes", 0),
                    "option3_votes": user_stats.get("option3_votes", 0),
                    "total_votes": user_stats.get("total_votes", 0),
                    "first_vote": user_stats.get("first_vote"),
                    "last_vote": user_stats.get("last_vote")
                }

                logger.info(f"Retrieved stats for user {user_id}: {stats['total_votes']} total votes")
                return stats

        except Exception as e:
            logger.error(f"Error fetching user stats for {user_id}: {e}", exc_info=True)
            return default_stats

    async def record_vote(self, question_id, user_id, guild_id, option):
        """
        Record a user's vote for a question (per-guild scoped) and update leaderboard.

        Per-user votes live in the ``daily_wyr_votes`` collection (one document per
        question/guild/user); the question document keeps only the bounded
        ``vote_counts`` aggregate.
        """
        try:
            with PerformanceLogger(logger, f"record_vote_{user_id}_{guild_id}_{option}"):
                gid = str(guild_id)
                uid = str(user_id)

                existing_question = await db_manager.daily_wyr.find_one({"_id": question_id})
                if not existing_question:
                    logger.error(f"Question {question_id} not found for vote recording")
                    return

                prior = await db_manager.daily_wyr_votes.find_one(
                    {"question_id": question_id, "guild_id": gid, "user_id": uid}
                )
                previous_vote = prior.get("option") if prior else None
                is_new_vote = previous_vote is None

                if not is_new_vote and previous_vote == option:
                    logger.info(
                        f"Recorded duplicate vote for user {user_id} on question {question_id} "
                        f"in guild {guild_id}: {option}"
                    )
                    return  # nothing changed

                now = datetime.now(timezone.utc)
                await db_manager.daily_wyr_votes.update_one(
                    {"question_id": question_id, "guild_id": gid, "user_id": uid},
                    {
                        "$set": {"option": option, "updated_at": now},
                        "$setOnInsert": {
                            "question_id": question_id,
                            "guild_id": gid,
                            "user_id": uid,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )

                # Keep the denormalized per-guild counts on the question document.
                if is_new_vote:
                    inc = {f"guilds.{gid}.vote_counts.{option}": 1}
                else:
                    inc = {
                        f"guilds.{gid}.vote_counts.{previous_vote}": -1,
                        f"guilds.{gid}.vote_counts.{option}": 1,
                    }
                await db_manager.daily_wyr.update_one({"_id": question_id}, {"$inc": inc})

                if is_new_vote:
                    await self.update_user_leaderboard(user_id, guild_id, option)

                vote_type = "new" if is_new_vote else "changed"
                logger.info(
                    f"Recorded {vote_type} vote for user {user_id} on question {question_id} in guild {guild_id}: {option}"
                )

        except Exception as e:
            logger.error(
                f"Error recording vote (user: {user_id}, guild: {guild_id}, question: {question_id}, option: {option}): {e}",
                exc_info=True,
            )

    async def get_question_results(self, question_id, guild_id):
        """
        Get voting results for a specific question scoped to a guild.
        """
        try:
            with PerformanceLogger(logger, f"get_question_results_{question_id}_{guild_id}"):
                gid = str(guild_id)
                question = await db_manager.daily_wyr.find_one({"_id": question_id})
                if not question:
                    logger.warning(f"Question {question_id} not found for results")
                    return None

                guild_data = (question.get("guilds") or {}).get(gid) or {}
                vote_counts = guild_data.get("vote_counts") or {"option1": 0, "option2": 0}
                has_option3 = bool(question.get("option_3"))
                total_votes = (
                    vote_counts.get("option1", 0)
                    + vote_counts.get("option2", 0)
                    + (vote_counts.get("option3", 0) if has_option3 else 0)
                )

                if total_votes > 0:
                    option1_percentage = (vote_counts.get("option1", 0) / total_votes) * 100
                    option2_percentage = (vote_counts.get("option2", 0) / total_votes) * 100
                else:
                    option1_percentage = option2_percentage = 0

                results = {
                    "option1_votes": vote_counts.get("option1", 0),
                    "option2_votes": vote_counts.get("option2", 0),
                    "option1_percentage": option1_percentage,
                    "option2_percentage": option2_percentage,
                    "total_votes": total_votes,
                }

                if has_option3:
                    option3_votes = vote_counts.get("option3", 0)
                    results["option3_votes"] = option3_votes
                    results["option3_percentage"] = (option3_votes / total_votes * 100) if total_votes > 0 else 0

                logger.info(f"Retrieved results for question {question_id}: {total_votes} total votes")
                return results

        except Exception as e:
            logger.error(f"Error getting question results for {question_id}: {e}", exc_info=True)
            return None

    async def get_user_vote(self, question_id, guild_id, user_id):
        """Return the option a user voted for on a question (or None)."""
        try:
            doc = await db_manager.daily_wyr_votes.find_one(
                {"question_id": question_id, "guild_id": str(guild_id), "user_id": str(user_id)}
            )
            return doc.get("option") if doc else None
        except Exception as e:
            logger.error(
                f"Error fetching user vote for {user_id} on question {question_id}: {e}",
                exc_info=True,
            )
            return None

    async def increment_used_count(self, question_id, guild_id):
        """
        Increment the per-guild `used_count` for a specific question.
        """
        try:
            gid = str(guild_id)
            success = await db_manager.daily_wyr.update_one(
                {"_id": question_id},
                {
                    "$inc": {f"guilds.{gid}.used_count": 1},
                    "$set": {f"guilds.{gid}.last_posted": datetime.now(timezone.utc)},
                },
            )

            if success:
                logger.info(f"Incremented used_count for question {question_id} in guild {guild_id}")
            else:
                logger.warning(
                    f"No document modified when incrementing used_count for question {question_id} in guild {guild_id}"
                )

        except Exception as e:
            logger.error(
                f"Error updating used_count for question {question_id} in guild {guild_id}: {e}",
                exc_info=True,
            )

    def create_question_embed(self, question, show_results=False, results=None):
        """
        Create a Discord embed for the WYR question.
        """
        try:
            description = (
                f"{OPTION1_EMOJI} **{question['option_1']}**\n"
                f"{OPTION2_EMOJI} **{question['option_2']}**"
            )
            if question.get('option_3'):
                description += f"\n{OPTION3_EMOJI} **{question['option_3']}**"

            embed = discord.Embed(
                title="❓ Would You Rather...",
                description=description,
                color=discord.Color.blue()
            )

            if show_results and results:
                results_text = (
                    f"{OPTION1_EMOJI} **{results['option1_percentage']:.1f}%** "
                    f"({results['option1_votes']} votes)\n"
                    f"{OPTION2_EMOJI} **{results['option2_percentage']:.1f}%** "
                    f"({results['option2_votes']} votes)\n"
                )
                if results.get('option3_votes') is not None:
                    results_text += (
                        f"{OPTION3_EMOJI} **{results['option3_percentage']:.1f}%** "
                        f"({results['option3_votes']} votes)\n"
                    )
                results_text += f"\n**Total Votes:** {results['total_votes']}"

                embed.add_field(
                    name=" Current Results",
                    value=results_text,
                    inline=False
                )

            embed.set_footer(text="Click a button to vote! • Results update in real-time")
            logger.debug(f"Created embed for question {question.get('_id', 'unknown')}")
            return embed

        except Exception as e:
            logger.error(f"Error creating question embed: {e}", exc_info=True)
            # Return a basic error embed
            return discord.Embed(
                title="❌ Error",
                description="Failed to create question embed",
                color=discord.Color.red()
            )


class WYRView(discord.ui.View):
    def __init__(self, question_id=None, cog=None, has_option3=False):
        super().__init__(timeout=None)
        self.question_id = question_id
        self.cog = cog
        if has_option3:
            btn = discord.ui.Button(
                label="Option 3", style=discord.ButtonStyle.primary,
                emoji=OPTION3_EMOJI, custom_id="wyr:option3"
            )
            btn.callback = self.option3_callback
            # Insert before Show Results (which is at index 2 after Option 1, Option 2)
            self.add_item(btn)
            # Reorder: move Option 3 (now last) before Show Results
            items = list(self.children)
            items.insert(2, items.pop())
            self.clear_items()
            for item in items:
                self.add_item(item)
        # Sits on its own row under the vote buttons: joining the ping role is
        # one click from any question, old posts included.
        self.add_item(wyr_notify.NotifyButton())
        if question_id:
            logger.debug(f"Created WYRView for question {question_id} (has_option3={has_option3})")

    def _get_cog(self, interaction: discord.Interaction):
        """Get the cog instance from the bot"""
        cog = interaction.client.get_cog("WYR")
        if not cog:
            logger.error("WYR cog not found when handling button interaction")
            raise RuntimeError("WYR cog not available")
        return cog

    @discord.ui.button(label="Option 1", style=discord.ButtonStyle.primary, emoji=OPTION1_EMOJI,
                       custom_id="wyr:option1")
    async def option1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(
            f"Option 1 vote button clicked by {interaction.user} (ID: {interaction.user.id}) for question {self.question_id}")
        await self.handle_vote(interaction, "option1")

    @discord.ui.button(label="Option 2", style=discord.ButtonStyle.primary, emoji=OPTION2_EMOJI,
                       custom_id="wyr:option2")
    async def option2_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(
            f"Option 2 vote button clicked by {interaction.user} (ID: {interaction.user.id}) for question {self.question_id}")
        await self.handle_vote(interaction, "option2")

    async def option3_callback(self, interaction: discord.Interaction):
        logger.info(
            f"Option 3 vote button clicked by {interaction.user} (ID: {interaction.user.id}) for question {self.question_id}")
        await self.handle_vote(interaction, "option3")

    @discord.ui.button(label="Show Results", style=discord.ButtonStyle.secondary, custom_id="wyr:results")
    async def show_results_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(
            f"Show results button clicked by {interaction.user} (ID: {interaction.user.id}) for question {self.question_id}")

        try:
            with PerformanceLogger(logger, f"show_results_{self.question_id}"):
                # Get the cog instance dynamically
                cog = self._get_cog(interaction)

                # Extract question_id from the message using mapping
                question_id = self.question_id
                if not question_id:
                    question_id = await cog.get_question_id_from_message(interaction.message.id)

                if not question_id:
                    logger.error(f"Could not determine question ID for results request from {interaction.user}")
                    await interaction.response.send_message("❌ Could not determine which question to show results for.",
                                                            ephemeral=True)
                    return

                results = await cog.get_question_results(question_id, interaction.guild_id)
                if not results:
                    logger.warning(f"Could not fetch results for question {question_id}")
                    await interaction.response.send_message("❌ Could not fetch results.", ephemeral=True)
                    return

                # Look up which option this user voted for
                user_vote = await cog.get_user_vote(question_id, interaction.guild_id, interaction.user.id)

                embed = discord.Embed(
                    title=" Current Results",
                    color=discord.Color.green()
                )

                # Create visual progress bars
                def create_bar(percentage, length=20):
                    filled = int(percentage / 100 * length)
                    return "█" * filled + "░" * (length - filled)

                bar1 = create_bar(results['option1_percentage'])
                bar2 = create_bar(results['option2_percentage'])

                pick1 = " **<< Your pick**" if user_vote == "option1" else ""
                pick2 = " **<< Your pick**" if user_vote == "option2" else ""

                embed.add_field(
                    name=f"{OPTION1_EMOJI} Option 1",
                    value=f"{bar1} {results['option1_percentage']:.1f}% ({results['option1_votes']} votes){pick1}",
                    inline=False
                )
                embed.add_field(
                    name=f"{OPTION2_EMOJI} Option 2",
                    value=f"{bar2} {results['option2_percentage']:.1f}% ({results['option2_votes']} votes){pick2}",
                    inline=False
                )

                if results.get('option3_votes') is not None:
                    bar3 = create_bar(results['option3_percentage'])
                    pick3 = " **<< Your pick**" if user_vote == "option3" else ""
                    embed.add_field(
                        name=f"{OPTION3_EMOJI} Option 3",
                        value=f"{bar3} {results['option3_percentage']:.1f}% ({results['option3_votes']} votes){pick3}",
                        inline=False
                    )

                embed.add_field(
                    name=" Total Votes",
                    value=f"{results['total_votes']} people have voted",
                    inline=False
                )

                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True,
                    **await wyr_notify.prompt_kwargs(interaction.user),
                )
                logger.info(f"Successfully showed results for question {question_id} to {interaction.user}")

        except Exception as e:
            logger.error(f"Error showing results: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while fetching results.", ephemeral=True)

    async def handle_vote(self, interaction: discord.Interaction, option):
        try:
            with PerformanceLogger(logger, f"handle_vote_{option}"):
                # Get the cog instance dynamically
                cog = self._get_cog(interaction)

                # Extract question_id from the message using mapping
                question_id = self.question_id
                if not question_id:
                    question_id = await cog.get_question_id_from_message(interaction.message.id)

                if not question_id:
                    logger.error(f"Could not determine question ID for vote from {interaction.user}")
                    await interaction.response.send_message("❌ Could not determine which question you're voting on.",
                                                            ephemeral=True)
                    return

                await cog.record_vote(question_id, interaction.user.id, interaction.guild_id, option)

                option_text = {"option1": "Option 1", "option2": "Option 2", "option3": "Option 3"}[option]
                embed = discord.Embed(
                    title="✅ Vote Recorded!",
                    description=f"You voted for **{option_text}**",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Your vote has been saved • You can change your vote anytime")

                # Riding along with the confirmation: members who already have
                # the ping role (or who said no thanks) get nothing extra.
                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True,
                    **await wyr_notify.prompt_kwargs(interaction.user),
                )
                logger.info(f"Vote successfully processed for {interaction.user} (ID: {interaction.user.id}): {option}")

        except Exception as e:
            logger.error(f"Error handling vote from {interaction.user} (ID: {interaction.user.id}): {e}", exc_info=True)
            try:
                await interaction.response.send_message(
                    "❌ There was an error recording your vote. Please try again.",
                    ephemeral=True
                )
            except:
                logger.error(f"Failed to send error message to {interaction.user}")


async def setup(bot):
    logger.info("Setting up WYR cog")
    try:
        await bot.add_cog(WYR(bot))
        logger.info("WYR cog successfully added to bot")
    except Exception as e:
        logger.error(f"Failed to setup WYR cog: {e}", exc_info=True)
        raise