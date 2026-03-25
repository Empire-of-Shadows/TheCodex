import os
import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.reactions = True
intents.emojis = True
intents.guild_messages = True

bot = commands.Bot(
    command_prefix=".",
    intents=intents,
    help_command=None,
    shard_id=0,
    shard_count=1
)

# Configuration defaults
TIMEZONE_NAME = "America/Chicago"

# Minimum similarity score to consider a match (for guide/search functionality)
SIMILARITY_THRESHOLD = 80

# Logging indent helper
s = " " * 10

# Expose the handler if needed in codex.py
__all__ = [
    "bot", "TOKEN",
    "SIMILARITY_THRESHOLD", "s",
    "TIMEZONE_NAME"
]
