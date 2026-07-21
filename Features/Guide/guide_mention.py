"""
Guide Mention Listener

When the bot is mentioned in a message, searches the guide for relevant content
and renders the result using Components V2 via GuideRenderer.

Replaces the old KEYWORD_MAP-based approach with search-based matching.
"""

import os
import time

from discord.ext import commands

from Features.Guide.guide import guide_manager
from storage.settings.config_manager import get_config
from storage.log import get_logger

logger = get_logger("GuideMentionListener")

# Per-user throttle so a single user can't spam mention-triggered searches.
_COOLDOWN_SECONDS = 2.0
_last_used: dict[tuple[int, int], float] = {}


def _on_cooldown(guild_id: int, user_id: int) -> bool:
	now = time.monotonic()
	key = (guild_id, user_id)
	if now - _last_used.get(key, 0.0) < _COOLDOWN_SECONDS:
		return True
	_last_used[key] = now
	# Opportunistic prune so the map can't grow without bound.
	if len(_last_used) > 10000:
		cutoff = now - 60
		for k, t in list(_last_used.items()):
			if t < cutoff:
				_last_used.pop(k, None)
	return False

# Generic help trigger words
HELP_WORDS = {
	"help", "assistance", "guidance", "support", "info", "information",
	"instructions", "how to", "manual", "faq", "troubleshoot",
	"troubleshooting", "guide", "explanation", "overview", "help menu",
	"usage", "tips", "learn", "details", "advice", "solution", "issues",
}

# Minimum search score to show a result (lower = more permissive)
_CONFIDENCE_THRESHOLD = 40

# Other bots allowed to trigger guide help on a mentioned user's behalf.
# Configured per-deployment via GUIDE_ALLOWED_BOT_IDS (comma-separated ids);
# empty by default so only human mentions trigger the guide.
_ALLOWED_BOT_IDS = {
    int(x) for x in os.getenv("GUIDE_ALLOWED_BOT_IDS", "").split(",") if x.strip().isdigit()
}


class HelpListener(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.Cog.listener()
	async def on_message(self, message):
		# Ignore non-allowed bots
		if message.author.bot and message.author.id not in _ALLOWED_BOT_IDS:
			return

		if self.bot.user not in message.mentions:
			return

		# Must be in a guild
		if not message.guild:
			return

		# Respect the per-guild guide toggle - stay silent where an admin
		# has turned the guide off.
		config = await get_config(message.guild.id)
		if not config.guide.get("enabled", True):
			return

		# Throttle per user to prevent mention spam from hammering search.
		if _on_cooldown(message.guild.id, message.author.id):
			return

		content = message.content.lower().strip()
		guild_id = message.guild.id

		# Who are we helping?
		if message.author.bot:
			mentioned_users = [m for m in message.mentions if m.id != self.bot.user.id]
			if not mentioned_users:
				return
			user_id = mentioned_users[0].id
		else:
			user_id = message.author.id

		# Strip bot mention from content for cleaner search
		clean = content
		for mention_format in [f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"]:
			clean = clean.replace(mention_format, "").strip()

		guild = message.guild
		member = message.author

		if not clean:
			# Just a mention with no query - show how-to-use instructions and tips
			layout = await guide_manager.get_usage_view(guild_id, user_id, guild=guild, member=member)
			await message.channel.send(view=layout)
			return

		# Generic help words → guide Home page. Checked before search so a help
		# word always lands on Home rather than jumping to a matching page.
		if any(word in clean for word in HELP_WORDS):
			logger.info("Generic help triggered")
			layout = await guide_manager.get_home_view(guild_id, user_id, guild=guild, member=member)
			await message.channel.send(view=layout)
			return

		# Non-help word (trigger word) - search the guide
		results = await guide_manager.search_content(clean, guild_id, user_id)

		if results and results[0]["score"] >= _CONFIDENCE_THRESHOLD:
			best = results[0]
			logger.info(f"Search match: '{clean}' -> '{best['name']}' (score {best['score']})")
			layout = await guide_manager.get_page_view(guild_id, user_id, best["page_id"], guild=guild, member=member)
			await message.channel.send(view=layout)
			return

		# No match - open the guide's Home page
		logger.info(f"No matches found for: '{clean}'")
		layout = await guide_manager.get_home_view(guild_id, user_id, guild=guild, member=member)
		await message.channel.send(view=layout)


async def setup(bot):
	await guide_manager.initialize_database()
	await bot.add_cog(HelpListener(bot))
