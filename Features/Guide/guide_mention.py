"""
Guide Mention Listener

When the bot is mentioned in a message, searches the guide for relevant content
and renders the result using Components V2 via GuideRenderer.

Replaces the old KEYWORD_MAP-based approach with search-based matching.
"""

from discord.ext import commands

from Features.Guide.guide import guide_manager
from utils.logger import get_logger

logger = get_logger("GuideMentionListener")

# Generic help trigger words
HELP_WORDS = {
	"help", "assistance", "guidance", "support", "info", "information",
	"instructions", "how to", "manual", "faq", "troubleshoot",
	"troubleshooting", "guide", "explanation", "overview", "help menu",
	"usage", "tips", "learn", "details", "advice", "solution", "issues",
}

# Minimum search score to show a result (lower = more permissive)
_CONFIDENCE_THRESHOLD = 40

# Todo - Remove hard coded values
# Allow messages from selected bots by ID only
_ALLOWED_BOT_IDS = [1324702268666417192, 1324623083646095453]


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
			# Just a mention with no query — show main menu
			layout = await guide_manager.get_root_menu(guild_id, user_id, guild=guild, member=member)
			await message.channel.send(view=layout)
			return

		# Search the guide
		results = await guide_manager.search_content(clean, guild_id, user_id)

		if results and results[0]["score"] >= _CONFIDENCE_THRESHOLD:
			best = results[0]
			logger.info(f"Search match: '{clean}' -> '{best['name']}' (score {best['score']})")
			layout = await guide_manager.get_page_view(guild_id, user_id, best["page_id"], guild=guild, member=member)
			await message.channel.send(view=layout)
			return

		# Check for generic help words
		if any(word in clean for word in HELP_WORDS):
			logger.info("Generic help triggered")
			layout = await guide_manager.get_root_menu(guild_id, user_id, guild=guild, member=member)
			await message.channel.send(view=layout)
			return

		# No match — show guide menu as fallback
		logger.info(f"No matches found for: '{clean}'")
		layout = await guide_manager.get_root_menu(guild_id, user_id, guild=guild, member=member)
		await message.channel.send(view=layout)


async def setup(bot):
	await guide_manager.initialize_database()
	await bot.add_cog(HelpListener(bot))
