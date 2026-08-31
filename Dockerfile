# Multi-stage Dockerfile for AI Codebase Agent.
#
# Stage 1 (frontend-builder): installs Node deps and produces a Next.js static
# export under /out.
#
# Stage 2 (runtime): a slim Python image that installs only the runtime
# requirements, copies the backend + code_intelligence + agent + retrieval +
# mcp source, copies the static frontend into /app/static, and runs uvicorn.
# The backend mounts /app/static at "/" with a SPA fallback so one process
# serves both the API and the frontend.

FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_PUBLIC_API_BASE_URL=/api
RUN npm run build

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: ripgrep is optional (used by the lexical search engine when
# available; the pure-Python fallback works without it). curl is used by the
# HEALTHCHECK below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ripgrep curl \
 && rm -rf /var/lib/apt/lists/*

# Python deps.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# App source.
COPY backend/ ./backend/
COPY code_intelligence/ ./code_intelligence/
COPY retrieval/ ./retrieval/
COPY agent/ ./agent/
COPY mcp/ ./mcp/
COPY pyproject.toml ./

# Built frontend (Next.js static export).
COPY --from=frontend-builder /build/frontend/out ./static

# Persistent uploads directory — mount a volume here in production.
RUN mkdir -p /app/uploaded_repos
ENV UPLOAD_ROOT=/app/uploaded_repos \
    STATIC_DIR=/app/static

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

# Single uvicorn worker is correct: the registry is in-memory. Horizontal
# scaling requires the deferred Postgres phase.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]