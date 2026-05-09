"""Dashboard configuration - environment variables and constants.

Canonical env names (read first, with legacy fallbacks during cutover):
- GATEKEEPER_CLIENT_ID / GATEKEEPER_CLIENT_SECRET / GATEKEEPER_REDIRECT_URI
- MONGO_PRIMARY_URI (was THECODEX)
- SHARED_SESSIONS_URI (canonical Mongo for WebSessions.SharedSessions)
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_first(*names: str, default: str = "") -> str:
    """Return the first non-empty env var from names, else default."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# Discord OAuth2 - shared GateKeeper bot across the ecosystem
DASHBOARD_CLIENT_ID = _env_first("GATEKEEPER_CLIENT_ID", "DASHBOARD_CLIENT_ID")
DASHBOARD_CLIENT_SECRET = _env_first("GATEKEEPER_CLIENT_SECRET", "DASHBOARD_CLIENT_SECRET")

# Codex bot token - used to check which guilds the bot is in
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
REDIRECT_URI = _env_first(
    "GATEKEEPER_REDIRECT_URI",
    "DASHBOARD_REDIRECT_URI",
    default="http://localhost:54002/auth/discord/callback",
)
DISCORD_API_BASE = "https://discord.com/api/v10"

# MongoDB - Codex's primary data
MONGO_URI = _env_first("MONGO_PRIMARY_URI", "THECODEX")

# MongoDB - shared session store. Codex's primary IS the canonical store, but
# we read it via a separate variable so the code matches Host/Ecom.
SHARED_SESSIONS_URI = _env_first("SHARED_SESSIONS_URI", "MONGO_PRIMARY_URI", "THECODEX")

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
