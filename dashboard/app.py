"""FastAPI application for the ImperialCodex web dashboard."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard import db
from dashboard.config import CORS_ORIGINS
from dashboard.auth.oauth import router as auth_router
from dashboard.routers.dashboard import router as dashboard_router
from dashboard.routers.builder import router as builder_router
from dashboard.routers.activity import router as activity_router
from dashboard.routers.validate import router as validate_router
from dashboard.routers.docs import router as docs_router

_frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
_index_html = os.path.join(_frontend_dist, "index.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="ImperialCodex Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API and auth routes (registered first so they take priority)
app.include_router(auth_router, prefix="/auth")
app.include_router(dashboard_router, prefix="/api")
app.include_router(activity_router, prefix="/api")
app.include_router(builder_router, prefix="/api")
app.include_router(validate_router, prefix="/api")
app.include_router(docs_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve static assets (JS, CSS, images) from Vite build
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")


# SPA fallback — any unmatched GET returns index.html for client-side routing
@app.get("/{path:path}")
async def spa_fallback(request: Request, path: str):
    if os.path.isfile(_index_html):
        return FileResponse(_index_html)
    return {"error": "Frontend not built. Run: cd dashboard/frontend && npm run build"}


if __name__ == "__main__":
    import uvicorn
    from dashboard.config import HOST, PORT

    uvicorn.run("dashboard.app:app", host=HOST, port=PORT, reload=True)
