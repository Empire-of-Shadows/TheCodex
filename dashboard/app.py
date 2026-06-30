"""FastAPI application for the TheCodex web dashboard."""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard import db
from dashboard.auth.csrf import csrf_endpoint, csrf_middleware
from dashboard.auth.session import (
    ensure_oauth_state_ttl_index,
    ensure_session_ttl_index,
)
from dashboard.config import CORS_ORIGINS, IS_PRODUCTION
from dashboard.rate_limit import rate_limit_middleware
from dashboard.auth.oauth import router as auth_router
from dashboard.routers.dashboard import router as dashboard_router
from dashboard.routers.builder import router as builder_router
from dashboard.routers.activity import router as activity_router
from dashboard.routers.validate import router as validate_router
from dashboard.routers.docs import router as docs_router
from dashboard.routers.public_stats import router as public_stats_router
from dashboard.routers.audit_log import router as audit_log_router
from dashboard.routers.settings import router as settings_router
from dashboard.routers.user_data import router as user_data_router
from storage.logging import get_logger

startup_logger = get_logger("dashboard.startup")
health_logger = get_logger("dashboard.health")

_frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend", "dist"))
_frontend_public = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend", "public"))
_index_html = os.path.join(_frontend_dist, "index.html")
_START_TIME = time.time()

# CSP matched to the SPA's asset origins: bundled JS/CSS from self, Google Fonts,
# and images from any https origin (guide markdown previews can embed external
# images). No inline scripts are emitted by the Vite build, so script-src is
# 'self' with no 'unsafe-inline'.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_logger.info("Dashboard starting up")
    await db.connect()
    # Codex owns the canonical session Mongo - ensure TTL indexes exist.
    await ensure_oauth_state_ttl_index()
    await ensure_session_ttl_index()
    startup_logger.info("Dashboard ready (frontend_built=%s)", os.path.isfile(_index_html))
    yield
    startup_logger.info("Dashboard shutting down")
    await db.close()


app = FastAPI(title="TheCodex Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(csrf_middleware)
app.middleware("http")(rate_limit_middleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = _CSP
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


app.add_api_route("/auth/csrf", csrf_endpoint, methods=["GET"])
# API and auth routes (registered first so they take priority)
app.include_router(auth_router, prefix="/auth")
app.include_router(dashboard_router, prefix="/api")
app.include_router(activity_router, prefix="/api")
app.include_router(builder_router, prefix="/api")
app.include_router(validate_router, prefix="/api")
app.include_router(docs_router, prefix="/api")
app.include_router(public_stats_router, prefix="/api")
app.include_router(audit_log_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(user_data_router, prefix="/api")


@app.get("/health")
async def health():
    response = {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "TheCodex Dashboard",
        "component": "TheCodex Dashboard - WebUI",
        "uptime": int(time.time() - _START_TIME),
        "frontend_built": os.path.isfile(_index_html),
    }
    try:
        client = db._get_client()
        await client.admin.command("ping")
        response["database_connected"] = True
        response["checks"] = {"database": {"status": "healthy"}}
    except Exception:
        health_logger.warning("Mongo health ping failed", exc_info=True)
        response["database_connected"] = False
        response["checks"] = {"database": {"status": "unhealthy"}}
        response["status"] = "degraded"
    return response


# Serve static assets (JS, CSS, images) from Vite build
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")


# SPA fallback — any unmatched GET returns index.html for client-side routing.
# Before falling back, serve any real file shipped in `dist/` or `public/`
# (favicons, brand images, robots.txt, etc.) directly so the SPA fallback
# doesn't swallow them. `public/` is checked second to cover the case where
# `dist/` hasn't been rebuilt after new assets were added.
@app.get("/{path:path}")
async def spa_fallback(request: Request, path: str):
    if path and ".." not in path:
        for root in (_frontend_dist, _frontend_public):
            candidate = os.path.normpath(os.path.join(root, path))
            if candidate.startswith(root) and os.path.isfile(candidate):
                return FileResponse(candidate)
    if os.path.isfile(_index_html):
        return FileResponse(_index_html)
    return {"error": "Frontend not built. Run: cd dashboard/frontend && npm run build"}


if __name__ == "__main__":
    import uvicorn
    from dashboard.config import HOST, PORT

    # Reload (file-watching, extra process) only in development. The container
    # entrypoint is `python -m dashboard.app`, so this path runs in production.
    uvicorn.run("dashboard.app:app", host=HOST, port=PORT, reload=not IS_PRODUCTION)
