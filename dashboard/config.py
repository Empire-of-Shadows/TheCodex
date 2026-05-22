"""Dashboard configuration - environment variables and constants."""

import os
from dotenv import load_dotenv

load_dotenv()


# Discord OAuth2 - shared GateKeeper bot across the ecosystem
DASHBOARD_CLIENT_ID = os.getenv("GATEKEEPER_CLIENT_ID", "")
DASHBOARD_CLIENT_SECRET = os.getenv("GATEKEEPER_CLIENT_SECRET", "")
if not DASHBOARD_CLIENT_ID:
    raise RuntimeError("GATEKEEPER_CLIENT_ID environment variable is required")
if not DASHBOARD_CLIENT_SECRET:
    raise RuntimeError("GATEKEEPER_CLIENT_SECRET environment variable is required")

# Codex bot token - used to check which guilds the bot is in
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
REDIRECT_URI = os.getenv(
    "GATEKEEPER_REDIRECT_URI",
    "http://localhost:54002/auth/discord/callback",
)
DISCORD_API_BASE = "https://discord.com/api/v10"

# MongoDB - single canonical URI for everything (codex data + shared sessions)
MONGO_URI = os.getenv("MONGO_URI", "")

# Session signing (itsdangerous URLSafeTimedSerializer key)
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("DASHBOARD_SECRET_KEY environment variable is required")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "eos_session")
SESSION_MAX_AGE_DAYS = int(os.getenv("SESSION_MAX_AGE_DAYS", "30"))

# Cookie domain — set to ".empireofshadows.club" in production for cross-subdomain SSO
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

# Server
HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
PORT = int(os.getenv("DASHBOARD_PORT", "54002"))

# CORS — filter falsy entries so an unset BASE_URL doesn't leak an empty origin.
CORS_ORIGINS = [
    o
    for o in [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:54002",
        "http://127.0.0.1:54002",
        os.getenv("BASE_URL"),
    ]
    if o
]

# Discord permission flag for MANAGE_GUILD
MANAGE_GUILD_PERMISSION = 0x20