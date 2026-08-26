# Backend image: FastAPI + code-intelligence engine + agent + MCP server.
#
# NOTE: This image is provided as scaffolding and has NOT been built/tested in
# this environment (Docker is not installed here). Treat it as a starting point.
#
# ripgrep is installed so the search engine uses its fast path; the pure-Python
# fallback still works if it is ever absent.

FROM python:3.12-slim

# System deps: ripgrep (fast search) + git (snapshot identity via `git rev-parse`).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App source (build context is the repo root; see docker-compose.yml).
COPY code_intelligence ./code_intelligence
COPY retrieval ./retrieval
COPY agent ./agent
COPY backend ./backend
COPY mcp ./mcp
COPY pyproject.toml ./

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Repositories are registered by absolute path. In a container that means paths
# INSIDE the container — mount host code read-only and set ALLOWED_REPO_ROOTS to
# the mount point (see docker-compose.yml).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
