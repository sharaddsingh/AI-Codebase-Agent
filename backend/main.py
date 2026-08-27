"""FastAPI application entrypoint.

    uvicorn backend.main:app --reload --port 8000

Wires together configuration, structured logging, CORS for the frontend, the
code-intelligence routers, and the SSE agent endpoint. Domain errors
(:class:`CodeIntelError`) are mapped to clean JSON responses with the right HTTP
status; unexpected errors are logged and returned as a generic 500 (no internals
leak to the client).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from code_intelligence.errors import CodeIntelError

from .config import get_settings
from .deps import get_registry
from .logging_config import configure_logging
from .routers import agent, files, health, repositories, search

log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.allowed_roots_list() is None:
        log.warning(
            "ALLOWED_REPO_ROOTS is empty: repository registration is UNRESTRICTED. "
            "Set it in production to constrain which paths can be registered."
        )
    log.info(
        "backend starting",
        extra={"extra": {
            "provider": settings.model_provider,
            "model_configured": settings.model_configured,
        }},
    )

    # Optional convenience: auto-register a repo for demos (local path or GitHub URL).
    if settings.default_repo_path:
        try:
            info = get_registry().register(settings.default_repo_path)
            log.info("auto-registered default repo", extra={"extra": {"repo_id": info.id}})
        except CodeIntelError as exc:
            log.warning("could not auto-register default repo: %s", exc.message)

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
    description="Read-only, tool-using agent that investigates local and GitHub repositories.",
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


@app.get("/")
def root() -> dict:
    return {"service": "ai-codebase-agent", "docs": "/docs", "health": f"{API}/health"}
