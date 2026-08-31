# Deployment guide

The project ships as a single Docker image (frontend + backend in one
process) plus Render and Fly.io manifests. The backend is a regular FastAPI
process; the frontend is a Next.js **static export** that the backend serves at
`/` with an SPA fallback.

## Build / run locally with Docker

```bash
cp .env.example .env            # fill in ANTHROPIC_API_KEY and GITHUB_TOKEN
docker build -t ai-codebase-agent .
docker run --rm -p 8000:8000 \
  -e ANTHROPIC_API_KEY \
  -e GITHUB_TOKEN \
  -v ai-codebase-agent-uploads:/app/uploaded_repos \
  ai-codebase-agent
```

Open <http://localhost:8000>. The volume at `/app/uploaded_repos` must be
persistent — without it, uploaded folders are wiped on every container restart.

## Render (Blueprint)

1. Push your repo to GitHub.
2. In Render, **New → Blueprint**, point at the repo. Render reads
   [`render.yaml`](../render.yaml) at the repo root.
3. The dashboard will create the web service and the persistent disk for
   uploads. Set `CORS_ORIGINS` and the two secret env vars
   (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`) in the service's **Environment**
   tab.
4. The first deploy takes a few minutes (it builds the Next.js frontend in
   `frontend-builder` and then the runtime image). Health check is
   `/api/health`.

### Render troubleshooting
- **`502 Bad Gateway` after deploy** — the backend booted but the Next.js
  frontend failed to build. Open the `frontend-builder` build logs.
- **Uploads disappear between deploys** — confirm the disk is mounted at
  `/var/data/uploaded_repos` and that `UPLOAD_ROOT` matches.

## Fly.io

```bash
fly launch --copy-config     # one-time, picks region + app name
fly volumes create uploads --size 1
fly secrets set ANTHROPIC_API_KEY=sk-ant-... GITHUB_TOKEN=ghp_...
fly deploy
```

[`fly.toml`](../fly.toml) at the repo root declares the app, the build, the
volume mount at `/data/uploaded_repos`, and a `/api/health` HTTP check.
Override `CORS_ORIGINS` with `fly secrets set CORS_ORIGINS=...` (or in
`fly.toml`).

### Fly troubleshooting
- **`unhealthy` machine** — `fly logs` will show the uvicorn startup. The most
  common cause is a missing `ANTHROPIC_API_KEY` or `GITHUB_TOKEN`.
- **Volume not attached** — confirm `fly volumes list` shows `uploads` and that
  `[[mounts]]` in `fly.toml` points at the right destination path.

## Single-host Docker (VPS / bare-metal)

The image runs unchanged on any host that can run OCI containers. Reverse-proxy
it with Caddy or nginx for TLS:

```caddyfile
ai-codebase-agent.example.com {
  reverse_proxy localhost:8000
}
```

Persistent volume for `/app/uploaded_repos` (Docker named volume, host bind
mount, or networked filesystem) is mandatory.

## Environment variables

All settings come from environment variables; see [`.env.example`](../.env.example)
for the full list. The values that matter for production:

- `MODEL_PROVIDER` — `anthropic` (real Claude) or `mock` (deterministic, no key).
- `ANTHROPIC_API_KEY` — required for `anthropic`.
- `GITHUB_TOKEN` — required for GitHub repository registration. The remote
  GitHub MCP server rejects unauthenticated requests even for public repos.
- `UPLOAD_ROOT` — must point at a persistent directory in production.
- `CORS_ORIGINS` — comma-separated list of frontend origins. For the bundled
  single-image deploy, set it to the production URL of the service.
- `STATIC_DIR` — where the backend looks for the static frontend. Defaults to
  `./static`, which matches the Docker image.

## What the backend does NOT do in production yet

The repository registry, the GitHub MCP session, and the upload pipeline are
all **in-memory** per process. Restarting the backend loses them.

This is fine for the single-image, single-region deployment we ship today. It
becomes a problem the moment you want to:

- scale horizontally (multiple uvicorn workers / instances)
- survive a restart with uploads intact **without** the persistent volume
- persist citation history or evaluation runs

The deferred phase for these is in [ROADMAP.md](ROADMAP.md) (Postgres + Redis +
S3-style upload storage).