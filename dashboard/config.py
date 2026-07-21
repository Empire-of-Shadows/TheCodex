"""Dashboard configuration - environment variables and constants."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "docker" / ".env")


# Discord OAuth2 - shared GateKeeper bot across the ecosystem
DASHBOARD_CLIENT_ID = os.getenv("GATEKEEPER_CLIENT_ID", "")
DASHBOARD_CLIENT_SECRET = os.getenv("GATEKEEPER_CLIENT_SECRET", "")
if not DASHBOARD_CLIENT_ID:
    raise RuntimeError("GATEKEEPER_CLIENT_ID environment variable is required")
if not DASHBOARD_CLIENT_SECRET:
    raise RuntimeError("GATEKEEPER_CLIENT_SECRET environment variable is required")

# Codex bot token - used to check which guilds the bot is in
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
REDIRECT_URI = os.getenv("GATEKEEPER_REDIRECT_URI") or os.getenv(
    "REDIRECT_URI",
    "http://localhost:54010/auth/discord/callback",
)
DISCORD_API_BASE = "https://discord.com/api/v10"

# MongoDB - codex's own data.
MONGO_URI = os.getenv("MONGO_URI", "")
# Shared cross-bot session store (WebSessions DB). A dedicated URI/client keeps the
# shared SSO store separate from codex's own data (matching relay); defaults to
# MONGO_URI so a deployment that hasn't split them yet keeps working.
SHARED_SESSIONS_URI = os.getenv("SHARED_SESSIONS_URI", "") or MONGO_URI

# Session signing (itsdangerous URLSafeTimedSerializer key)
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("DASHBOARD_SECRET_KEY environment variable is required")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "eos_session")
SESSION_MAX_AGE_DAYS = int(os.getenv("SESSION_MAX_AGE_DAYS", "30"))

# Cookie domain - set to ".eosofficial.club" in production for cross-subdomain SSO
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)
# Production mode drives the Secure flag on the shared session cookie. Accept either
# convention (ENVIRONMENT=production OR IS_PRODUCTION=1/true/yes) so codex and relay
# behave identically regardless of which spelling a deployment sets.
IS_PRODUCTION = (
    os.getenv("ENVIRONMENT", "").lower() == "production"
    or os.getenv("IS_PRODUCTION", "").lower() in ("1", "true", "yes")
)

# Server
HOST = os.getenv("DASHBOARD_HOST") or os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("DASHBOARD_PORT") or os.getenv("PORT", "54010"))

# CORS - filter falsy entries so an unset BASE_URL doesn't leak an empty origin.
CORS_ORIGINS = [
    o
    for o in [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:54010",
        "http://127.0.0.1:54010",
        os.getenv("BASE_URL"),
    ]
    if o
]

# Discord permission flags
MANAGE_GUILD_PERMISSION = 0x20
ADMINISTRATOR_PERMISSION = 0x8

# ── Shared dashboard-engine seam values (read by dashboard/_engine/) ──────────
# OAuth redirect allowlist (regex, anchored ^...$) + fallback, used by _engine/auth/oauth.py.
OAUTH_REDIRECT_ALLOWLIST = r"^https?://(localhost(:\d+)?|([a-z0-9-]+\.)?eosofficial\.club)(/.*)?$"
OAUTH_DEFAULT_REDIRECT = "/dashboard"

# Rate-limit route table for _engine/rate_limit.py: (path-prefix, bucket, max, window_s).
# First match wins, so specific prefixes precede their parents.
RATE_LIMITS: list[tuple[str, str, int, int]] = [
    ("/auth/discord/callback", "oauth_callback", 10, 60),
    ("/auth/discord", "oauth_start", 20, 60),
    ("/api/me", "me", 100, 60),
    ("/api/stats/public", "public_stats", 30, 60),
]


def _validate_config() -> None:
    """Fail fast on missing/misconfigured environment rather than 500ing later.

    The dashboard cannot function without the bot token (live guild checks) and
    the Mongo URI. In production, the Secure cookie flag and CORS origin also
    depend on ENVIRONMENT/BASE_URL being set correctly - a silent wrong default
    there is a security regression.
    """
    required = {
        "DISCORD_TOKEN": BOT_TOKEN,
        "MONGO_URI": MONGO_URI,
    }
    missing = [name for name, val in required.items() if not val]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    if IS_PRODUCTION:
        if not os.getenv("BASE_URL"):
            raise RuntimeError(
                "BASE_URL must be set in production (used for the CORS origin "
                "and cookie scope)"
            )
        if "localhost" in REDIRECT_URI or "127.0.0.1" in REDIRECT_URI:
            raise RuntimeError(
                "GATEKEEPER_REDIRECT_URI still points at localhost in production"
            )


_validate_config()