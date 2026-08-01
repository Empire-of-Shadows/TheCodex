import os
import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Lean explicit intents (fleet standard - see TheHost / ImperialReminder / relay).
# `Intents.default()` used to be the base here, which switched on ~10 gateway
# intents nothing in this bot listens for: reactions, emojis_and_stickers,
# voice_states, typing, invites, webhooks, integrations, moderation (bans),
# scheduled_events, auto_moderation and dm_messages. Verified against every
# listener in Features/ commands/ admin/ storage/ before removal - none of them
# had a handler and no code reads the caches they populate.
#
# Each one below is load-bearing. Do not trim without re-checking the listener
# that needs it:
#   guilds          - on_guild_join/remove, on_guild_role_create/update/delete,
#                     on_guild_channel_update, on_guild_update, and the guild /
#                     channel / role caches the panel and dashboard resolve against.
#   members         - PRIVILEGED. on_member_join + on_member_remove (member
#                     screening, Features/NewMembers/joining.py), on_member_update
#                     (boost tracker), on_user_update (tag tracker). Dropping this
#                     silently kills all three.
#   guild_messages  - on_message (announcement threads, guide mention listener,
#                     drops tracker), on_message_edit + on_raw_message_delete.
#   message_content - PRIVILEGED. NOT needed for the guide: Discord delivers full
#                     content for messages that mention the bot even with this off,
#                     and guide_mention.py bails unless the bot is mentioned. It IS
#                     needed for two features that read messages which do not
#                     mention the bot:
#                       * announcements.py format_thread_name reads message.content
#                         to title the auto-thread ("💬 {message_content}").
#                       * drops-tracker.py _embeds_changed diffs message.embeds on
#                         edit; embeds are gated by this intent too, so without it
#                         every edit compares [] to [] and is dropped.
#                     Removing it means changing those two features first.
intents = discord.Intents.none()
intents.guilds = True
intents.members = True
intents.guild_messages = True
intents.message_content = True

bot = commands.Bot(
    # Slash-only: no "." text-command surface. The owner-only load_cogs utility is
    # still reachable by mentioning the bot (matches the relay reference).
    command_prefix=commands.when_mentioned,
    intents=intents,
    help_command=None,
    shard_id=0,
    shard_count=1,
    # Safe default so user-authored content the bot echoes (guide/greeting builder
    # text, etc.) can never ping @everyone/@here or roles. Individual user mentions
    # (e.g. the greeting "{member}" placeholder) still work. Features that
    # intentionally ping a role must pass an explicit allowed_mentions override.
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
)

# Configuration defaults
TIMEZONE_NAME = "America/Chicago"

# Minimum similarity score to consider a match (for guide/search functionality)
SIMILARITY_THRESHOLD = 80

# Logging indent helper
s = " " * 5

# Expose the handler if needed in Codex.py
__all__ = [
    "bot", "TOKEN",
    "SIMILARITY_THRESHOLD", "s",
    "TIMEZONE_NAME"
]
