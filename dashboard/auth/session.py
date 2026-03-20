"""Session CRUD for SharedSessions collection (cross-subdomain SSO)."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard import db
from dashboard.config import SESSION_MAX_AGE_DAYS


async def create_session(user_data: dict, guilds: list[dict]) -> str:
    """Create a new session and return the session token."""
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    doc = {
        "token": token,
        "user_id": user_data["id"],
        "user_data": user_data,
        "guilds": guilds,
        "guilds_fetched_at": now,
        "created_at": now,
        "last_accessed": now,
        "expires_at": now + timedelta(days=SESSION_MAX_AGE_DAYS),
    }
    await db.shared_sessions().insert_one(doc)
    return token


async def get_session(token: str) -> dict[str, Any] | None:
    """Look up a session by token. Returns None if expired or missing."""
    doc = await db.shared_sessions().find_one({"token": token})
    if doc is None:
        return None
    expires_at = doc.get("expires_at", datetime.min)
    # MongoDB stores naive datetimes — compare without timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if expires_at.replace(tzinfo=None) < now:
        await delete_session(token)
        return None
    # Update last_accessed timestamp
    await db.shared_sessions().update_one(
        {"token": token},
        {"$set": {"last_accessed": datetime.now(timezone.utc)}},
    )
    return doc


async def delete_session(token: str):
    """Delete a session by token."""
    await db.shared_sessions().delete_one({"token": token})
