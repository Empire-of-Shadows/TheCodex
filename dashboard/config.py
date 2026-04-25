"""Dashboard configuration — environment variables and constants."""

import os
from dotenv import load_dotenv

load_dotenv()

# Discord OAuth2 ( Uses a separate bot to act as an auth bot across the ecosystem - GateKeeper)
DASHBOARD_CLIENT_ID = os.getenv("DASHBOARD_CLIENT_ID", "")
DASHBOARD_CLIENT_SECRET = os.getenv("DASHBOARD_CLIENT_SECRET", "")

# Codex bot token — used to check which guilds the bot is in
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
REDIRECT_URI = os.getenv("DASHBOARD_REDIRECT_URI", "http://localhost:54002/auth/discord/callback")
DISCORD_API_BASE = "https://discord.com/api/v10"

    # MongoDB — reuses the bot's primary connection (THCODEX)
MONGO_URI = os.getenv("THECODEX", "")

# Session
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("DASHBOARD_SECRET_KEY environment variable is required")
SESSION_COOKIE_NAME = "eos_session"
SESSION_MAX_AGE_DAYS = 30

# Cookie domain — set to ".empireofshadows.club" in production for cross-subdomain SSO
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

# Server
HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
PORT = int(os.getenv("DASHBOARD_PORT", "54002"))

# CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:54002",
    "http://127.0.0.1:54002",
    os.getenv("BASE_URL", ""),
]

# Discord permission flag for MANAGE_GUILD
MANAGE_GUILD_PERMISSION = 0x20
