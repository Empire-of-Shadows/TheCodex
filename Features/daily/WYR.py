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
from Features.daily.wyr_bank import (
    FORMAT_LABELS,
    FORMAT_OPEN,
    FORMATS,
    MAX_OPTIONS,
    normalize_text_key,
    question_options,
    validate_question,
    wyr_bank,
)
from Features.daily.wyr_submissions import wyr_submissions
from Features.daily.wyr_submit_views import (
    RejectReasonModal,
    SubmissionBuilderView,
    SubmissionReviewView,
    build_decision_dm_embed,
    build_review_embed,
)
from startup.bot import s
from storage.log import get_logger, PerformanceLogger
from storage.settings.collections import db_manager
from storage.settings.config_manager import get_config, get_guild_config_manager
from admin.actions.wyr_question_actions import WYRQuestionActions
from admin.setup_notice import send_setup_notice

# Load environment variables
load_dotenv()

# Constants
OPTION1_EMOJI = "1️⃣"  # Reaction for option 1
OPTION2_EMOJI = "2️⃣"  # Reaction for option 2
OPTION3_EMOJI = "3️⃣"  # Reaction for option 3

#: Vote button emoji by option number. Indexed by ``question_options``, so the
#: ceiling here and ``MAX_OPTIONS`` move together.
OPTION_EMOJI = {1: OPTION1_EMOJI, 2: OPTION2_EMOJI, 3: OPTION3_EMOJI, 4: "4️⃣", 5: "5️⃣"}

# Outcomes of a scheduled post attempt. The distinction that matters is
# NO_CONTENT vs FAILED: the first is settled for the day, the second retries on
# the next tick.
POST_SENT = "sent"
POST_NO_CONTENT = "no_content"
POST_FAILED = "failed"

#: What a guild posts when its format list is missing or unusable. Mirrors
#: config_manager's own default so the two layers cannot disagree.
DEFAULT_QUESTION_FORMATS = ("wyr",)

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
    """Substitute supported placeholders in a WYR thread format string.

    ``{question_num}`` reads ``id``, the int question number (1..5006 in
    production), NOT ``_id``, which is an ObjectId. They are different fields
    and only one of them is meant for human eyes.
    """
    tags = question.get("tags") or []
    category = tags[0].title() if tags else "General"
    out = (
        template
        .replace("{date}",         now.strftime("%m/%d"))
        .replace("{question_num}", str(question.get("id", "")))
        .replace("{category}",     category)
        .replace("{question}",     question.get("original", ""))
    )
    # Options are substituted for every slot the format supports, so a template
    # written for one format degrades to empty text rather than a literal
    # "{option_4}" when it meets a question that has fewer.
    for n in range(1, MAX_OPTIONS + 1):
        out = out.replace(f"{{option_{n}}}", question.get(f"option_{n}") or "")
    return out


def _simple_layout(text: str) -> discord.ui.LayoutView:
    """A one-message LayoutView, for replacing an ephemeral flow with its result."""
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(text))
    view.add_item(container)
    return view


def _thread_templates(guild_config, question: dict) -> tuple:
    """Pick the (thread name, starter message) templates for a question's format.

    Each format gets its own pair rather than sharing one. It has to be that
    way: every guild's SAVED thread_starter_message contains literal
    "1️⃣ {option_1}" lines, so reusing it for a question with different options
    (or none) renders leftover numbering with nothing beside it. Rewriting a
    template an admin customized would be worse than carrying three keys.
    """
    wyr = guild_config.wyr
    fmt = question.get("format") or "wyr"
    if fmt == "poll":
        suffix = "_poll"
    elif fmt == FORMAT_OPEN:
        suffix = "_open"
    else:
        suffix = ""
    defaults = _default_thread_templates(suffix)
    return (
        wyr.get(f"thread_name_format{suffix}") or defaults[0],
        wyr.get(f"thread_starter_message{suffix}") or defaults[1],
    )


def _default_thread_templates(suffix: str) -> tuple:
    """Fallback templates, used only when a guild's config predates the key."""
    if suffix == "_poll":
        return "📊 QOTD · Q{question_num} · {date}", "📊 **{question}**"
    if suffix == "_open":
        return "💬 QOTD · Q{question_num} · {date}", "💬 **{question}**"
    return "🎲 WYR · Q{question_num} · {date}", "🎲 **{question}**"


class WYRCommandGroup(app_commands.Group):
    """Command group for Would You Rather commands"""

    def __init__(self, cog):
        # guild_only: every WYR command scopes its queries by guild_id, so a DM
        # invocation would run a None-keyed lookup. Marking the group guild-only
        # registers all its commands DM-unavailable.
        super().__init__(name="wyr", description="Would You Rather commands", guild_only=True)
        self.cog = cog

    @app_commands.command(
        name="submit",
        description="Suggest a question for the daily post (a moderator approves it)",
    )
    @app_commands.checks.cooldown(1, 60)
    async def wyr_submit(self, interaction: discord.Interaction):
        """Open the suggestion builder.

        Every refusal happens BEFORE anything is stored, and each one says
        something different. In particular a server with submissions on but no
        reviewer and no review channel is refused outright: accepting a
        suggestion nobody can ever see is the exact dead end this feature was
        built to remove.
        """
        logger.info(f"WYR submit opened by {interaction.user} in guild {interaction.guild_id}")

        try:
            settings = await WYRQuestionActions.get_submission_settings(interaction.guild_id)

            if not settings["enabled"]:
                await send_setup_notice(
                    interaction,
                    what="question suggestions",
                    path="WYR Settings -> Question Bank -> Member Suggestions",
                    detail="Suggestions are turned off in this server right now.",
                )
                return

            if not settings["review_channel_id"] and not settings["moderator_role_id"]:
                await interaction.response.send_message(
                    "Suggestions are turned on here, but nobody is set up to review "
                    "them yet, so yours would not reach anyone. Please let a server "
                    "admin know.",
                    ephemeral=True,
                )
                return

            waiting = await wyr_submissions.count_open_for_user(
                interaction.guild_id, interaction.user.id
            )
            if waiting >= settings["max_pending"]:
                await interaction.response.send_message(
                    f"You already have **{waiting}** suggestion(s) waiting to be "
                    f"reviewed. Once one of those is handled you can send another.",
                    ephemeral=True,
                )
                return

            formats = await WYRQuestionActions.get_question_formats(interaction.guild_id)
            view = SubmissionBuilderView(
                member_id=interaction.user.id,
                formats=formats,
                on_submit=self.cog.process_submission,
            )
            await interaction.response.send_message(view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error opening WYR submit for {interaction.user}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong opening the suggestion box.", ephemeral=True
                )

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
                # Options 3 and up only appear once the member has actually used
                # them, so a server posting two-option questions keeps the
                # compact layout it has always had.
                for number in range(3, MAX_OPTIONS + 1):
                    if stats.get(f"option{number}_votes", 0) > 0:
                        embed.add_field(
                            name=f"{OPTION_EMOJI[number]} Option {number} Votes",
                            value=f"{stats[f'option{number}_votes']:,}",
                            inline=True
                        )
                embed.add_field(
                    name="️ Total Votes",
                    value=f"{stats['total_votes']:,}",
                    inline=True
                )

                if stats['total_votes'] > 0:
                    total = stats['total_votes']
                    pref_lines = [
                        f"Option 1: {(stats['option1_votes'] / total) * 100:.1f}%",
                        f"Option 2: {(stats['option2_votes'] / total) * 100:.1f}%",
                    ]
                    for number in range(3, MAX_OPTIONS + 1):
                        votes = stats.get(f"option{number}_votes", 0)
                        if votes > 0:
                            pref_lines.append(f"Option {number}: {(votes / total) * 100:.1f}%")
                    embed.add_field(
                        name=" Voting Preference",
                        value="\n".join(pref_lines),
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

            # An open-ended question has no options, so there is nothing to
            # tally. Say so rather than drawing empty bars for options that do
            # not exist.
            if results.get("format") == FORMAT_OPEN:
                await interaction.response.send_message(
                    "That one is an open-ended question - there are no options to tally. "
                    "Jump into its thread and add your answer.",
                    ephemeral=True,
                )
                return

            # Create results embed
            embed = discord.Embed(
                title="📊 Question Results",
                color=discord.Color.green()
            )

            # Create visual progress bars
            def create_bar(percentage, length=20):
                filled = int(percentage / 100 * length)
                return "█" * filled + "░" * (length - filled)

            for entry in results.get("options") or []:
                bar = create_bar(entry["percentage"])
                embed.add_field(
                    name=f"{OPTION_EMOJI.get(entry['number'], '•')} {entry['text']}",
                    value=f"{bar} {entry['percentage']:.1f}% ({entry['votes']} votes)",
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
        # Register the view without question_id and cog - they will be set when needed.
        # Registered with the full option set so wyr:option4 and wyr:option5 also
        # resolve on a post that outlived a restart; the question id is recovered
        # from the message mapping when a button is actually clicked.
        self.bot.add_view(WYRView(option_count=MAX_OPTIONS))
        # Review posts outlive restarts too. Registered with no submission id;
        # the handlers recover it from the message the buttons sit on.
        self.bot.add_view(SubmissionReviewView())
        logger.info("Persistent WYRView and SubmissionReviewView registered after bot ready")

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
                        outcome = await self.post_daily_question_for_guild(guild_id, guild_config)
                    except Exception as e:
                        logger.error(f"Error posting WYR to guild {guild_id}: {e}", exc_info=True)
                        outcome = POST_FAILED
                    # "no_content" is a settled state, not a transient failure:
                    # a guild drawing only from its own empty bank has nothing to
                    # post and will still have nothing a minute from now. Treating
                    # it as a failure would re-evaluate that guild every minute for
                    # the rest of the day. Only a real failure retries.
                    if outcome in (POST_SENT, POST_NO_CONTENT):
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

    async def post_daily_question_for_guild(self, guild_id, guild_config) -> str:
        """
        Post a daily WYR question for a single guild using per-guild settings.

        Returns one of ``POST_SENT`` / ``POST_NO_CONTENT`` / ``POST_FAILED``.

        The three-way answer exists because "nothing to post" and "the post
        failed" need opposite handling. The caller retries a failure on the next
        tick, which is right for a permissions blip or a 5xx. It must NOT retry
        an empty bank: a guild drawing only from its own questions before it has
        added any would otherwise be re-evaluated every single minute for the
        rest of the day.
        """
        if not guild_config.wyr.get("enabled", False):
            return POST_NO_CONTENT

        logger.info(f"Posting scheduled WYR question for guild {guild_id}")

        try:
            with PerformanceLogger(logger, f"wyr_post_guild_{guild_id}"):
                channel = self.bot.get_channel(guild_config.wyr["channel_id"])
                if not channel:
                    # The channel may simply not be in cache yet after a restart,
                    # so this is a retryable failure rather than a settled state.
                    logger.warning(f"WYR channel {guild_config.wyr['channel_id']} not found for guild {guild_id}")
                    return POST_FAILED

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

                question = await self.get_next_question(
                    category,
                    guild_id=guild_id,
                    allow_nsfw=allow_nsfw,
                    question_source=guild_config.wyr.get("question_source", "both"),
                    question_formats=guild_config.wyr.get("question_formats"),
                )
                if not question:
                    logger.warning(
                        f"Guild {guild_id} has no {category} question available to post "
                        f"(source: {guild_config.wyr.get('question_source', 'both')}, "
                        f"formats: {guild_config.wyr.get('question_formats')}). Add questions "
                        f"through the admin panel under WYR Settings -> Question Bank."
                    )
                    return POST_NO_CONTENT

                embed = self.create_question_embed(question)
                view = self.build_question_view(question)

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

                # Read thread settings from guild config, per format
                thread_name_fmt, starter_msg = _thread_templates(guild_config, question)
                archive_dur = guild_config.wyr.get("thread_auto_archive", 1440)
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
                return POST_SENT

        except Exception as e:
            logger.error(f"Error posting WYR to guild {guild_id}: {e}", exc_info=True)
            return POST_FAILED

    async def post_question_now(self, channel, *, category=None,
                                random_pick=False) -> tuple:
        """Post one question to a channel on demand. Returns ``(ok, message)``.

        This is what `/wyr post` used to be. It moved here so the admin panel
        can drive it: the command was a subcommand of `/wyr`, and Discord only
        honours ``default_member_permissions`` on TOP-LEVEL commands, so there
        was no way to hide it from members who could never use it. `/wyr` itself
        has to stay visible - the rest of its commands are for everyone.

        The channel is explicit rather than "wherever you typed", which also
        means an admin can post to a channel they are not currently in.
        """
        guild = channel.guild
        guild_config = await get_config(guild.id)
        if category is None:
            category = guild_config.wyr.get("default_category", "sfw")

        # NSFW questions only go to age-restricted channels. An explicit NSFW
        # request is refused outright rather than quietly answered with an SFW
        # question, so the admin knows why.
        allow_nsfw = _channel_allows_nsfw(channel)
        if category == "nsfw" and not allow_nsfw:
            return False, (
                f"{channel.mention} is not age-restricted, so NSFW questions "
                f"cannot be posted there. Turn on **Age-Restricted Channel** in "
                f"that channel's settings, or choose the `sfw` category."
            )

        source = guild_config.wyr.get("question_source", "both")
        formats = guild_config.wyr.get("question_formats")
        fetch = self.get_random_question if random_pick else self.get_next_question
        question = await fetch(
            category, guild_id=guild.id, allow_nsfw=allow_nsfw,
            question_source=source, question_formats=formats,
        )
        if not question:
            return False, (
                f"There are no {category} questions available right now.\n"
                f"Add some under **Question Bank** above."
            )

        try:
            message = await channel.send(
                embed=self.create_question_embed(question),
                view=self.build_question_view(question),
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Could not post a WYR question to {channel.id}: {e}")
            return False, f"I could not post in {channel.mention}."

        await self.store_message_question_mapping(
            message.id, question["_id"], channel_id=channel.id, guild_id=guild.id
        )

        thread_name_fmt, starter_msg = _thread_templates(guild_config, question)
        tz = pytz.timezone(guild_config.wyr.get("timezone", "America/Chicago"))
        now = datetime.now(tz)
        try:
            thread = await message.create_thread(
                name=_format_wyr_string(thread_name_fmt, question, now)[:100],
                auto_archive_duration=guild_config.wyr.get("thread_auto_archive", 1440),
            )
            await thread.send(_format_wyr_string(starter_msg, question, now))
        except (discord.Forbidden, discord.HTTPException) as e:
            # The question is up; only the discussion thread failed.
            logger.warning(f"Posted WYR question but could not open its thread: {e}")

        # A manual post counts toward the rotation exactly like a scheduled one,
        # or the same question could come back the next morning.
        await self.increment_used_count(question["_id"], guild.id)
        logger.info(f"Posted WYR question {question.get('id')} on demand in guild {guild.id}")
        return True, (
            f"Posted question **#{question.get('id')}** in {channel.mention}.\n"
            f"[Jump to it]({message.jump_url})"
        )

    # ── Member submissions ───────────────────────────────────────────────

    async def process_submission(self, interaction, question_format, text, options, tags):
        """Store a member's suggestion and post it for review.

        Called from the builder's Send button. Everything that can refuse does
        so before the submission is stored, and if the review post cannot be
        delivered the submission is deleted again rather than left in a queue
        nobody can see.
        """
        guild_id = interaction.guild_id
        try:
            ok, cleaned, error = validate_question(question_format, text, options, tags)
            if not ok:
                await interaction.response.send_message(f"❌ {error}", ephemeral=True)
                return

            text_key = normalize_text_key(
                cleaned["format"], cleaned["original"],
                [v for _, v in question_options(cleaned)],
            )

            if await wyr_bank.find_duplicate(text_key, guild_id):
                await interaction.response.send_message(
                    "This server already has that question, so there is nothing to add.",
                    ephemeral=True,
                )
                return
            if await wyr_submissions.find_duplicate(guild_id, text_key):
                await interaction.response.send_message(
                    "Somebody has already suggested that one.", ephemeral=True
                )
                return

            settings = await WYRQuestionActions.get_submission_settings(guild_id)
            submission = await wyr_submissions.create_submission(
                guild_id=guild_id, user_id=interaction.user.id, cleaned=cleaned
            )
            if not submission:
                await interaction.response.send_message(
                    "❌ Could not save your suggestion. Please try again.", ephemeral=True
                )
                return

            posted = await self._post_submission_for_review(
                submission, guild_id, settings
            )
            if not posted:
                # Better that the member is told to try again than that their
                # question sits somewhere nobody will ever look.
                await wyr_submissions.delete_submission(submission["submission_id"])
                await interaction.response.send_message(
                    "❌ Your suggestion could not be sent to the review channel, so "
                    "it was not saved. Please let a server admin know.",
                    ephemeral=True,
                )
                return

            await interaction.response.edit_message(
                view=_simple_layout(
                    "✅ **Sent for review.**\n"
                    "A moderator will take a look. You will get a DM either way."
                )
            )
            logger.info(
                f"Submission {submission['submission_id'][:8]} queued in guild {guild_id}"
            )

        except Exception as e:
            logger.error(f"Error processing a submission in guild {guild_id}: {e}",
                         exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong sending your suggestion.", ephemeral=True
                )

    async def _post_submission_for_review(self, submission, guild_id, settings) -> bool:
        """Put the review post in the review channel. False if it could not be."""
        channel_id = settings.get("review_channel_id")
        if not channel_id:
            # A reviewer role with no channel is a valid setup: the queue is
            # worked through in the admin panel instead, under WYR Settings ->
            # Question Bank -> Member Suggestions -> Review Suggestions.
            return True

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                logger.warning(f"WYR review channel {channel_id} unreachable: {e}")
                return False

        warning = await WYRQuestionActions.warning_for_format(
            guild_id, submission.get("format")
        )
        try:
            message = await channel.send(
                embed=build_review_embed(submission, format_warning=warning),
                view=SubmissionReviewView(submission["submission_id"]),
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Could not post a WYR review message in guild {guild_id}: {e}")
            return False

        await wyr_submissions.set_review_message(
            submission["submission_id"], channel.id, message.id
        )
        return True

    async def _resolve_submission(self, interaction, view):
        """Find the submission behind a review post, or explain why not.

        A view rebuilt after a restart carries no id, so it is recovered from
        the message. Returns None having already answered the interaction.
        """
        submission_id = getattr(view, "submission_id", None)
        submission = None
        if submission_id:
            submission = await wyr_submissions.get_submission(submission_id)
        if submission is None:
            submission = await wyr_submissions.find_by_review_message(interaction.message.id)
        if submission is None:
            await interaction.response.send_message(
                "That suggestion is no longer on file.", ephemeral=True
            )
            return None
        return submission

    async def _reviewer_gate(self, interaction) -> bool:
        if await WYRQuestionActions.can_review(interaction.user):
            return True
        await interaction.response.send_message(
            "You do not have permission to review question suggestions.", ephemeral=True
        )
        return False

    async def handle_submission_nsfw_toggle(self, interaction, view):
        """Mark the pending question age-restricted before approving it."""
        if not await self._reviewer_gate(interaction):
            return
        submission = await self._resolve_submission(interaction, view)
        if submission is None:
            return

        view.nsfw = not getattr(view, "nsfw", False)
        view.submission_id = submission["submission_id"]
        state = "age-restricted" if view.nsfw else "not age-restricted"
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"This question will be added as **{state}**.", ephemeral=True
        )

    async def handle_submission_approve(self, interaction, view):
        """Approve a suggestion into the guild's own bank.

        Ordering matters and is not incidental: the submission is CLAIMED before
        anything is inserted. Without that, a double-click or two moderators
        acting at the same moment would both pass the status check and add the
        same question twice.
        """
        if not await self._reviewer_gate(interaction):
            return
        submission = await self._resolve_submission(interaction, view)
        if submission is None:
            return

        submission_id = submission["submission_id"]
        guild_id = interaction.guild_id

        if not await wyr_submissions.claim_for_review(submission_id, interaction.user.id):
            await interaction.response.send_message(
                "Somebody else already handled that one.", ephemeral=True
            )
            return

        try:
            # Re-checked after the claim: the question may have been added by
            # another route while this post sat in the channel.
            text_key = submission.get("text_key")
            if text_key and await wyr_bank.find_duplicate(text_key, guild_id):
                await wyr_submissions.release_claim(submission_id)
                await interaction.response.send_message(
                    "This server already has that question, so it was not added again.",
                    ephemeral=True,
                )
                return

            cleaned = {
                "format": submission.get("format") or "wyr",
                "original": submission.get("original", ""),
                "tags": list(submission.get("tags") or []),
            }
            for number, text in question_options(submission):
                cleaned[f"option_{number}"] = text

            question = await wyr_bank.insert_question(
                cleaned,
                guild_id=guild_id,
                source="submission",
                nsfw=bool(getattr(view, "nsfw", False)),
                submitted_by=submission.get("user_id"),
                approved_by=interaction.user.id,
            )
            if not question:
                # Put it back in the queue rather than stranding it as claimed.
                await wyr_submissions.release_claim(submission_id)
                await interaction.response.send_message(
                    "❌ Could not add that question. It has been put back in the queue.",
                    ephemeral=True,
                )
                return

            # The question NUMBER, not the ObjectId: this is what the submitter
            # and the reviewer are shown, and what mark_approved stores as an int.
            await wyr_submissions.mark_approved(
                submission_id, question["id"], interaction.user.id
            )
            await self._close_review_post(
                interaction, submission, outcome="approved",
                question_id=question["id"],
            )
            await self._notify_submitter(interaction, submission, approved=True)

            warning = await WYRQuestionActions.warning_for_format(
                guild_id, cleaned["format"]
            )
            if warning:
                await interaction.followup.send(
                    f"{warning}\nTurn it on under **WYR Settings -> Question Bank -> "
                    f"Question Types** in `/admin panel`.",
                    ephemeral=True,
                )
            logger.info(
                f"Submission {submission_id[:8]} approved as question "
                f"{question['id']} in guild {guild_id}"
            )

        except Exception as e:
            logger.error(f"Error approving submission {submission_id}: {e}", exc_info=True)
            await wyr_submissions.release_claim(submission_id)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong. The suggestion is back in the queue.",
                    ephemeral=True,
                )

    async def handle_submission_reject(self, interaction, view):
        """Decline a suggestion, optionally with a reason for the member."""
        if not await self._reviewer_gate(interaction):
            return
        submission = await self._resolve_submission(interaction, view)
        if submission is None:
            return

        submission_id = submission["submission_id"]

        async def _on_reason(modal_interaction, reason: str):
            if not await wyr_submissions.claim_for_review(
                submission_id, modal_interaction.user.id
            ):
                await modal_interaction.response.send_message(
                    "Somebody else already handled that one.", ephemeral=True
                )
                return
            await wyr_submissions.mark_rejected(
                submission_id, modal_interaction.user.id, reason
            )
            await self._close_review_post(
                modal_interaction, submission, outcome="rejected", reason=reason
            )
            await self._notify_submitter(
                modal_interaction, submission, approved=False, reason=reason
            )
            logger.info(f"Submission {submission_id[:8]} declined in guild {interaction.guild_id}")

        await interaction.response.send_modal(RejectReasonModal(_on_reason))

    async def _close_review_post(self, interaction, submission, *, outcome,
                                 question_id=None, reason=""):
        """Rewrite the review post to show the decision and drop its buttons."""
        embed = build_review_embed(
            submission,
            decided_by=interaction.user,
            outcome=outcome,
            reason=reason,
            question_id=question_id,
        )
        try:
            if interaction.response.is_done():
                await interaction.message.edit(embed=embed, view=None)
            else:
                await interaction.response.edit_message(embed=embed, view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Could not update a WYR review post: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Recorded, but the review post could not be updated.", ephemeral=True
                )

    async def _notify_submitter(self, interaction, submission, *, approved, reason=""):
        """DM the member the outcome. Best effort by design.

        Sent inline rather than through a queue: the click has already been
        answered, and a DM that cannot be delivered costs nothing - an approved
        question is in the bank and will post regardless.
        """
        try:
            user_id = int(submission.get("user_id"))
        except (TypeError, ValueError):
            return
        try:
            user = interaction.guild.get_member(user_id) or await self.bot.fetch_user(user_id)
            await user.send(embed=build_decision_dm_embed(
                submission,
                guild_name=interaction.guild.name,
                approved=approved,
                reason=reason,
            ))
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
            logger.info(
                f"Could not DM member {user_id} about submission "
                f"{str(submission.get('submission_id', ''))[:8]}"
            )

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
                        "score": 1,
                        "first_vote": now,
                        "last_vote": now,
                        "updated_at": now,
                    }
                    # A column per option, so a member whose first ever vote is
                    # option 4 still gets a complete row rather than one missing
                    # the field every later read expects.
                    for number in range(1, MAX_OPTIONS + 1):
                        new_user[f"option{number}_votes"] = (
                            1 if option_chosen == f"option{number}" else 0
                        )
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

    #: Matches the shared bank. A question with no ``scope`` at all predates
    #: private banks, and the bank was shared by every guild for its whole life
    #: before then - so missing means global. Without this the daily post would
    #: stop dead for every guild between deploying the code and running the
    #: backfill migration, which is an ordering dependency worth not having.
    _GLOBAL_SCOPE = {"$or": [{"scope": "global"}, {"scope": {"$exists": False}}]}

    @classmethod
    def _build_scope_clause(cls, gid_str: str | None, question_source: str) -> dict | None:
        """Build the filter deciding WHICH bank a guild draws from.

        Returns None when there is nothing this guild may ever be served, which
        is a settled state rather than a failure - "guild_only" with no guild.

        This clause is what keeps one server's private questions out of every
        other server. It is never optional, and never omitted on any code path.
        """
        if question_source == "global_only":
            return dict(cls._GLOBAL_SCOPE)
        if question_source == "guild_only":
            # A private question always carries both keys, so this branch needs
            # no legacy allowance - and must not have one, or a missing scope
            # would match every guild.
            return {"scope": "guild", "guild_id": gid_str} if gid_str else None
        if gid_str is None:
            return dict(cls._GLOBAL_SCOPE)
        return {"$or": [{"scope": "global"},
                        {"scope": {"$exists": False}},
                        {"scope": "guild", "guild_id": gid_str}]}

    @staticmethod
    def _build_formats_clause(question_formats) -> dict:
        """Restrict selection to the formats this guild posts.

        A question predating the format field is a Would You Rather, so when
        "wyr" is enabled the clause also accepts documents with no format at
        all - otherwise every question in the bank today would stop being
        selectable the moment this shipped.

        An empty or unrecognizable list falls back to the same default
        ``config_manager`` uses, NOT to "post everything". Treating no
        selection as every selection would let a corrupt value post a format
        the server had deliberately switched off, and would put the runtime at
        odds with the config layer, which already normalizes empty to ["wyr"].
        """
        wanted = [f for f in (question_formats or []) if f in FORMATS]
        if not wanted:
            wanted = list(DEFAULT_QUESTION_FORMATS)
        if len(wanted) == len(FORMATS):
            # Every format is wanted, so there is nothing to narrow.
            return {}
        if "wyr" in wanted:
            return {"$or": [{"format": {"$in": wanted}}, {"format": {"$exists": False}}]}
        return {"format": {"$in": wanted}}

    @classmethod
    def _assemble_question_query(cls, category, allow_nsfw, gid_str,
                                 question_source, question_formats,
                                 used_path=None, exclude_used=False) -> dict | None:
        """Combine the category, scope, format and usage filters into one query.

        Deliberately an explicit ``$and`` of independent clauses rather than one
        merged dict. Several of these clauses want a top-level ``$or``, and a
        dict can only hold one - merging them would let the last writer silently
        drop an earlier clause. If that clause were the scope filter, the result
        is a guild being served another server's private questions, with no
        error anywhere. Keep the clauses separate.
        """
        base = cls._build_category_query(category, allow_nsfw)
        if base is None:
            return None

        scope = cls._build_scope_clause(gid_str, question_source)
        if scope is None:
            return None

        clauses = [base, scope]

        formats = cls._build_formats_clause(question_formats)
        if formats:
            clauses.append(formats)

        if exclude_used and used_path:
            # Treat missing nested key (never posted in this guild) as zero.
            clauses.append({"$or": [
                {used_path: {"$exists": False}},
                {used_path: 0},
            ]})

        clauses = [c for c in clauses if c]
        if not clauses:
            return {}
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    async def get_next_question(self, category="sfw", guild_id=None, exclude_used=False,
                                allow_nsfw=False, question_source="both",
                                question_formats=None):
        """
        Fetch the next "Would You Rather" question for a guild - least-used in that guild first.
        """
        try:
            with PerformanceLogger(logger, f"get_next_question_{category}_{guild_id}"):
                gid_str = str(guild_id) if guild_id is not None else None
                used_path = f"guilds.{gid_str}.used_count" if gid_str else "used_count"

                query = self._assemble_question_query(
                    category, allow_nsfw, gid_str, question_source, question_formats,
                    used_path=used_path, exclude_used=exclude_used,
                )
                if query is None:
                    logger.warning(
                        f"No question can be served to guild {guild_id}: category is "
                        f"{category} (channel age-restricted: {allow_nsfw}), source is "
                        f"{question_source}"
                    )
                    return None

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

    async def get_random_question(self, category="sfw", guild_id=None, allow_nsfw=False,
                                  question_source="both", question_formats=None):
        """
        Get a random question from the specified category using the new DatabaseManager.

        Carries the same scope and format filters as ``get_next_question``. It
        has to: without the scope clause this path would happily hand a guild a
        random question out of another server's private bank.
        """
        try:
            with PerformanceLogger(logger, f"get_random_question_{category}"):
                gid_str = str(guild_id) if guild_id is not None else None
                match_filter = self._assemble_question_query(
                    category, allow_nsfw, gid_str, question_source, question_formats,
                )
                if match_filter is None:
                    logger.warning(
                        f"No random question can be served to guild {guild_id}: category "
                        f"is {category} (channel age-restricted: {allow_nsfw}), source is "
                        f"{question_source}"
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
        default_stats = {f"option{n}_votes": 0 for n in range(1, MAX_OPTIONS + 1)}
        default_stats["total_votes"] = 0

        try:
            with PerformanceLogger(logger, f"get_user_stats_{user_id}_{guild_id}"):
                user_stats = await db_manager.daily_wyr_leaderboard.find_one(
                    {"user_id": str(user_id), "guild_id": str(guild_id)}
                )

                if not user_stats:
                    logger.info(f"No stats found for user {user_id} in guild {guild_id}")
                    return dict(default_stats)

                stats = {
                    f"option{n}_votes": user_stats.get(f"option{n}_votes", 0)
                    for n in range(1, MAX_OPTIONS + 1)
                }
                stats.update({
                    "total_votes": user_stats.get("total_votes", 0),
                    "first_vote": user_stats.get("first_vote"),
                    "last_vote": user_stats.get("last_vote"),
                })

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
                vote_counts = guild_data.get("vote_counts") or {}
                options = question_options(question)

                # Only count options the question actually has. A stale
                # vote_counts entry for an option since removed must not inflate
                # the total and skew every percentage.
                total_votes = sum(vote_counts.get(f"option{n}", 0) for n, _ in options)

                results = {
                    "format": question.get("format") or "wyr",
                    "total_votes": total_votes,
                    "options": [],
                }
                for number, text in options:
                    votes = vote_counts.get(f"option{number}", 0)
                    percentage = (votes / total_votes * 100) if total_votes > 0 else 0
                    results["options"].append({
                        "number": number,
                        "text": text,
                        "votes": votes,
                        "percentage": percentage,
                    })
                    # Flat per-option keys kept alongside the list: /wyr results,
                    # the Show Results button and the embed builder all read them.
                    results[f"option{number}_votes"] = votes
                    results[f"option{number}_percentage"] = percentage

                # An option-less question still answers with zeroes rather than
                # a missing key, so a caller that reads option1_votes on one
                # gets 0 instead of a KeyError.
                for number in (1, 2):
                    results.setdefault(f"option{number}_votes", 0)
                    results.setdefault(f"option{number}_percentage", 0)

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

    def build_question_view(self, question):
        """Build the right view for a question's format.

        An open-ended question has nothing to vote on, so it gets a view with
        only the notification button rather than a set of dead vote buttons.
        """
        if question.get("format") == FORMAT_OPEN:
            return OpenQuestionView()
        return WYRView(
            question["_id"],
            self,
            option_count=len(question_options(question)),
        )

    def create_question_embed(self, question, show_results=False, results=None):
        """
        Create a Discord embed for a daily question.

        Would You Rather keeps the presentation it has always had: a fixed
        title and the options alone, with the ``original`` text deliberately
        not shown. The other two formats lead with the question text, because
        for them the options are the answer rather than the question.
        """
        try:
            fmt = question.get("format") or "wyr"
            options = question_options(question)

            if fmt == FORMAT_OPEN:
                # No option lines at all. Reading option_1 here used to raise
                # KeyError, land in the handler below and post a red "Error"
                # embed to the whole server.
                embed = discord.Embed(
                    title="💬 Question of the Day",
                    description=question.get("original", ""),
                    color=discord.Color.blurple(),
                )
                embed.set_footer(text="Jump into the thread and share your answer!")
                logger.debug(f"Created open-question embed for {question.get('_id', 'unknown')}")
                return embed

            option_lines = "\n".join(
                f"{OPTION_EMOJI.get(number, '•')} **{text}**" for number, text in options
            )

            if fmt == "poll":
                title = "📊 Question of the Day"
                description = f"{question.get('original', '')}\n\n{option_lines}"
                color = discord.Color.green()
            else:
                title = "❓ Would You Rather..."
                description = option_lines
                color = discord.Color.blue()

            embed = discord.Embed(title=title, description=description, color=color)

            if show_results and results:
                lines = []
                for entry in results.get("options") or []:
                    emoji = OPTION_EMOJI.get(entry["number"], "•")
                    lines.append(
                        f"{emoji} **{entry['percentage']:.1f}%** ({entry['votes']} votes)"
                    )
                results_text = "\n".join(lines)
                results_text += f"\n\n**Total Votes:** {results['total_votes']}"

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


class OpenQuestionView(discord.ui.View):
    """Persistent view for an open-ended question - discussion only.

    Deliberately NOT registered with ``bot.add_view``: its only component is
    ``wyr:notify``, which the persistent WYRView already registers. Registering
    the same custom_id twice would shadow the first handler.
    """

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(wyr_notify.NotifyButton())


class WYRView(discord.ui.View):
    def __init__(self, question_id=None, cog=None, has_option3=False, option_count=None):
        super().__init__(timeout=None)
        self.question_id = question_id
        self.cog = cog

        # Options 1 and 2 stay as class-level decorated buttons below. Every
        # question ever posted resolves its votes through those two custom_ids
        # after a restart, so they are not made dynamic. Options 3 to 5 are
        # added here instead.
        if option_count is None:
            option_count = 3 if has_option3 else 2
        try:
            option_count = int(option_count)
        except (TypeError, ValueError):
            option_count = 2
        option_count = max(2, min(option_count, MAX_OPTIONS))
        self.option_count = option_count

        for number in range(3, option_count + 1):
            btn = discord.ui.Button(
                label=f"Option {number}", style=discord.ButtonStyle.primary,
                emoji=OPTION_EMOJI[number], custom_id=f"wyr:option{number}"
            )
            btn.callback = self._make_vote_callback(number)
            self.add_item(btn)

        if option_count > 2:
            # The decorated buttons put Show Results at index 2, so the extra
            # options land after it. Move it back to the end by custom_id
            # rather than by index, which stays correct however many were added.
            options = [c for c in self.children
                       if getattr(c, "custom_id", "") != "wyr:results"]
            results = [c for c in self.children
                       if getattr(c, "custom_id", "") == "wyr:results"]
            self.clear_items()
            for item in options + results:
                self.add_item(item)

        # Sits on its own row under the vote buttons: joining the ping role is
        # one click from any question, old posts included.
        self.add_item(wyr_notify.NotifyButton())
        if question_id:
            logger.debug(f"Created WYRView for question {question_id} ({option_count} options)")

    def _make_vote_callback(self, option_number: int):
        """Bind one vote callback per option.

        A factory, not a lambda in the loop: a closure over the loop variable
        would leave every button voting for the last option.
        """
        async def _callback(interaction: discord.Interaction):
            logger.info(
                f"Option {option_number} vote button clicked by {interaction.user} "
                f"(ID: {interaction.user.id}) for question {self.question_id}"
            )
            await self.handle_vote(interaction, f"option{option_number}")
        return _callback

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

                if results.get("format") == FORMAT_OPEN:
                    await interaction.response.send_message(
                        "That one is an open-ended question - there are no options to "
                        "tally. Jump into its thread and add your answer.",
                        ephemeral=True,
                    )
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

                for entry in results.get("options") or []:
                    bar = create_bar(entry["percentage"])
                    pick = " **<< Your pick**" if user_vote == f"option{entry['number']}" else ""
                    embed.add_field(
                        name=f"{OPTION_EMOJI.get(entry['number'], '•')} {entry['text']}",
                        value=f"{bar} {entry['percentage']:.1f}% ({entry['votes']} votes){pick}",
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