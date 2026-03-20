"""Discord OAuth2 routes with cross-subdomain SSO support."""

import re
import secrets
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from dashboard.auth.session import create_session, delete_session
from dashboard.config import (
    COOKIE_DOMAIN,
    DASHBOARD_CLIENT_ID,
    DASHBOARD_CLIENT_SECRET,
    DISCORD_API_BASE,
    IS_PRODUCTION,
    REDIRECT_URI,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_DAYS,
)

router = APIRouter(tags=["auth"])

_SCOPES = "identify guilds"
_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
_TOKEN_URL = f"{DISCORD_API_BASE}/oauth2/token"

# In-memory storage for OAuth states (short-lived)
_oauth_states: dict[str, str] = {}

_ALLOWED_REDIRECT_PATTERN = re.compile(
    r"^https?://(localhost(:\d+)?|([a-z0-9-]+\.)?empireofshadows\.club)(/.*)?"
)


def _validate_redirect(url: str | None) -> str:
    """Validate redirect_to URL is on an allowed domain. Falls back to /dashboard."""
    if url and _ALLOWED_REDIRECT_PATTERN.match(url):
        return url
    return "/dashboard"


@router.get("/discord")
async def discord_login(redirect_to: str | None = None):
    """Redirect to Discord OAuth2 authorization page."""
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = _validate_redirect(redirect_to)

    params = {
        "client_id": DASHBOARD_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
    }
    return RedirectResponse(f"{_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/discord/callback")
async def discord_callback(code: str, state: str | None = None, response: Response = None):
    """Exchange authorization code for tokens, fetch user info, create session."""
    # Validate state
    redirect_url = "/dashboard"
    if state and state in _oauth_states:
        redirect_url = _oauth_states.pop(state)
    elif state is not None:
        return RedirectResponse(url="/login", status_code=302)

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": DASHBOARD_CLIENT_ID,
                "client_secret": DASHBOARD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        access_token = tokens["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}

        # Fetch user info
        user_resp = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
        user_resp.raise_for_status()
        user_data = user_resp.json()

        # Fetch guilds
        guilds_resp = await client.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
        guilds_resp.raise_for_status()
        guilds = guilds_resp.json()

    # Create session
    session_token = await create_session(user_data, guilds)

    # Redirect to originating page with session cookie
    redirect = RedirectResponse(url=redirect_url, status_code=302)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=IS_PRODUCTION,
        domain=COOKIE_DOMAIN,
    )
    return redirect


@router.get("/logout")
async def logout(request: Request):
    """Delete session and clear cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await delete_session(token)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME, domain=COOKIE_DOMAIN)
    return response
