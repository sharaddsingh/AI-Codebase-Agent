"""FastAPI application entrypoint.

    uvicorn backend.main:app --reload --port 8000

Wires together configuration, structured logging, CORS for the frontend, the
code-intelligence routers, and the SSE agent endpoint. Domain errors
(:class:`CodeIntelError`) are mapped to clean JSON responses with the right HTTP
status; unexpected errors are logged and returned as a generic 500 (no internals
leak to the client).

When a static frontend build exists at ``./static`` (the default output of
``next build`` with ``output: "export"``), this app also serves those assets at
``/`` so a single uvicorn process hosts both the API and the SPA. The static
mount only kicks in when the directory is present, so local dev (where the
frontend runs on its own dev server) is unaffected.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from code_intelligence.errors import CodeIntelError

from .config import get_settings
from .deps import get_registry, rehydrate_github_repos, rehydrate_uploads
from .logging_config import configure_logging
from .routers import agent, files, health, repositories, search

log = logging.getLogger("backend")

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "./static")).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    log.info(
        "backend starting",
        extra={"extra": {
            "provider": settings.model_provider,
            "model_configured": settings.model_configured,
            "static_dir": str(STATIC_DIR) if STATIC_DIR.exists() else "(none)",
        }},
    )

    # Bring back uploads a previous process left on disk. The registry is
    # in-memory, so without this every restart orphans the folders in the
    # upload root and the browser is left holding ids that 404. Never fatal:
    # the app must start even if the upload root is unreadable.
    try:
        revived = rehydrate_uploads()
        if revived:
            log.info("restored uploaded repos", extra={"extra": {"count": revived}})
    except Exception:  # noqa: BLE001 - startup must not depend on the upload root
        log.warning("could not restore uploaded repos", exc_info=True)

    # GitHub registrations are persisted in a sidecar JSON next to the upload
    # root. Without this a backend restart would silently forget every
    # registered GitHub repo while the frontend kept the same id, leaving
    # the UI wedged on "No repository registered with id ..." for every
    # DELETE / file-tree call.
    try:
        revived_gh = rehydrate_github_repos()
        if revived_gh:
            log.info("restored github repos", extra={"extra": {"count": revived_gh}})
    except Exception:  # noqa: BLE001 - startup must not depend on github state
        log.warning("could not restore github repos", exc_info=True)

    yield

    # Shutdown: close the shared GitHub MCP session (if one was opened) so the
    # loop thread and remote session do not leak across a backend restart.
    try:
        get_registry().close_github_mcp()
    except Exception:  # noqa: BLE001 - best-effort cleanup on shutdown
        log.warning("error closing GitHub MCP session on shutdown", exc_info=True)


app = FastAPI(
    title="AI Codebase Engineering Agent",
    version="0.1.0",
    description="Read-only, tool-using agent that investigates browser-uploaded and GitHub repositories.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(CodeIntelError)
async def _handle_code_intel_error(_: Request, exc: CodeIntelError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})


@app.exception_handler(Exception)
async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal server error."}},
    )


API = "/api"
app.include_router(health.router, prefix=API)
app.include_router(repositories.router, prefix=API)
app.include_router(files.router, prefix=API)
app.include_router(search.router, prefix=API)
app.include_router(agent.router, prefix=API)


# ---- Root / static frontend (SPA fallback) --------------------------------
# When the Next.js static export exists at STATIC_DIR, mount it at "/" and
# route every non-API GET to index.html so client-side routing works on
# hard refresh. Local dev (frontend on its own dev server) skips this block
# and serves a small API descriptor at "/" instead.
#
# These two are deliberately mutually exclusive: an unconditional JSON route
# at "/" would win the exact-path match against the catch-all below and make
# the deployed landing page return JSON instead of the app.

if STATIC_DIR.exists():
    # Serve files that physically exist in the export (/_next/*, /favicon.ico, etc).
    app.mount(
        "/_next",
        StaticFiles(directory=STATIC_DIR / "_next", check_dir=False),
        name="next-assets",
    )
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir, check_dir=False),
            name="static-assets",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Never shadow API or docs endpoints — those are handled by routers above.
        if full_path.startswith("api/") or full_path in ("docs", "openapi.json", "redoc"):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": "Not found."}},
            )
        index = STATIC_DIR / "index.html"
        # Try the on-disk path first (e.g. /favicon.ico), then fall back to the
        # SPA shell. `full_path` is "" for "/", which must go straight to the
        # shell rather than being joined onto STATIC_DIR.
        if full_path:
            candidate = STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Not found."}},
        )

else:

    @app.get("/")
    def root() -> dict:
        return {"service": "ai-codebase-agent", "docs": "/docs", "health": f"{API}/health"}
