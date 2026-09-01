# Setup guide

A step-by-step walkthrough to get **AI Codebase Agent** running locally from
scratch. The architecture overview and full env-var reference live in
[README.md](README.md) and [docs/](docs/).

> **TL;DR** — install Python + Node deps, copy `.env.example` → `.env`, then run
> the backend (`uvicorn`), the frontend (`npm run dev`), and open
> http://localhost:3000. No API key? Set `MODEL_PROVIDER=mock`.

---

## 1. Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10+ (dev: 3.13) | `python --version` |
| Node.js | 18+ (dev: 22) | `node --version` |
| npm | 9+ | `npm --version` |
| ripgrep | *optional* (fast search) | `rg --version` |
| Anthropic API key | *optional* (use `mock` instead) | — |
| GitHub token | *required* for GitHub repos via MCP | — |

If `python` maps to Python 2 on your system, use `python3` everywhere below.

---

## 2. Configure environment

From the repository root:

```bash
cp .env.example .env
```

Open `.env` and choose one of:

- **Anthropic Claude (default):** set `MODEL_PROVIDER=anthropic` and
  `ANTHROPIC_API_KEY=sk-ant-...`. Uses Anthropic's native Messages API.
- **Any OpenAI-compatible host (TaBiToken, OpenRouter, llama.cpp with an
  OpenAI shim, vLLM, Ollama, ...):** set `MODEL_PROVIDER=openai`, then
  `OPENAI_API_KEY=...` and `OPENAI_BASE_URL=<host root, no /v1>`.
  `OPENAI_MODEL=<the model name>` (e.g. `gpt-4o-mini` for OpenAI proper or
  whatever your host exposes).
- **Without any key (recommended for a first run):** set `MODEL_PROVIDER=mock`.

> **Anthropic-only:** `ANTHROPIC_BASE_URL` only works with hosts that speak
> Anthropic's native Messages API. Most third-party gateways are
> OpenAI-compatible — if you see `<!DOCTYPE html>` or `PermissionDeniedError`
> with HTML in the error message, switch to `MODEL_PROVIDER=openai` and use
> `OPENAI_BASE_URL` against the same host.

For GitHub repositories, also set `GITHUB_TOKEN=ghp_...` — the official remote
GitHub MCP server requires a token even for public repos.

Everything else has working defaults. `.env` is git-ignored — never commit it.

---

## 3. Python backend, engine, and agent

Create and activate a virtual environment, then install dependencies.

**Windows (PowerShell):**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

`requirements.txt` is the runtime; `requirements-dev.txt` adds pytest, ruff, and
mypy.

---

## 4. Frontend

```bash
cd frontend
npm install
cd ..
```

Optionally point the frontend at a non-default backend URL:

```bash
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > frontend/.env.local
```

---

## 5. (Optional) Install ripgrep for fast search

Search works without it (pure-Python fallback), but ripgrep is faster.

- **Windows:** `winget install BurntSushi.ripgrep.MSVC` (or `choco install ripgrep`)
- **macOS:** `brew install ripgrep`
- **Debian/Ubuntu:** `sudo apt-get install ripgrep`

---

## 6. Run the services

Open a terminal per service (activate the venv in each Python terminal).

**① Backend** — http://localhost:8000 (interactive API docs at `/docs`):
```bash
uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --reload-dir retrieval --reload-dir code_intelligence --port 8000
```

> The `--reload-dir` flags matter. Uploads land in `./uploaded_repos/`, inside
> the project, so a bare `--reload` watches them too: upload any folder
> containing a `.py` file and the reloader restarts the server, which wipes the
> in-memory registry and makes the folder you just uploaded disappear. Scoping
> the watcher to the source packages fixes that and still reloads on code edits.

**② Frontend** — http://localhost:3000:
```bash
cd frontend && npm run dev
```

**③ MCP server** *(optional — only to connect an external MCP client such as
Claude Desktop; the web app does not need it)*:
```bash
python mcp/server.py
```

---

## 7. First-run smoke test

### Via the UI

1. Open **http://localhost:3000**.
2. Click **Upload** and drop a folder from your computer. (Or click **GitHub**
   and paste a URL like `facebook/react`.)
3. Browse the file tree and open a file in the viewer.
4. In the chat, ask: **"How does authentication work?"**
5. Watch the activity rail (classify → plan → tool calls → answer) and the
   citation chips populate with clickable `file:line` references.

### Via curl (backend only)

```bash
# Health
curl http://localhost:8000/api/health

# Register a GitHub repo (returns JSON including its "id")
curl -X POST http://localhost:8000/api/repositories/github \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/octocat/Hello-World"}'

# Upload a folder (replace @repo with a directory you want to register)
curl -X POST http://localhost:8000/api/repositories/upload \
  -F "files=@path/to/file1.py" \
  -F "files=@path/to/file2.py"

# Ask the agent (SSE stream). Replace <REPO_ID> with the id from above.
curl -N -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"repo_id": "<REPO_ID>", "question": "How does authentication work?"}'
```

With `MODEL_PROVIDER=mock` the agent returns a deterministic scripted response —
useful to confirm the full request → stream path before wiring a real key.

---

## 8. Tests, lint, and type checks

**Python** (repo root, venv active):
```bash
python -m pytest
python -m ruff check .
python -m mypy code_intelligence retrieval agent backend
```

**Frontend** (from `frontend/`):
```bash
npx tsc --noEmit
npm run lint
```

---

## 9. Deployment

The included `Dockerfile` builds a single image that runs the FastAPI backend
and serves the prebuilt Next.js frontend from the same origin. Render and
Fly.io manifests are provided for one-click deploys. See
[docs/DEPLOY.md](docs/DEPLOY.md) for the full guide.

```bash
docker build -t ai-codebase-agent .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY \
  -e GITHUB_TOKEN \
  -v ai-codebase-agent-uploads:/app/uploaded_repos \
  ai-codebase-agent
```

Mount a persistent volume at `/app/uploaded_repos` (or wherever `UPLOAD_ROOT`
points) so uploaded folders survive container restarts.

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Frontend loads but every call fails | Backend not running, or `NEXT_PUBLIC_API_BASE_URL` doesn't match the backend URL. Start the backend first. |
| CORS error in browser console | Add the frontend origin to `CORS_ORIGINS` in `.env` (default already allows `http://localhost:3000`). |
| Chat error "model not configured" | `MODEL_PROVIDER=anthropic` but `ANTHROPIC_API_KEY` is empty. Set the key, or switch to `MODEL_PROVIDER=mock`. |
| GitHub register fails with auth error | `GITHUB_TOKEN` is missing. The remote GitHub MCP server mandates a token even for public repos. |
| Upload fails with "file count exceeds limit" | Browser-picked folder is too large; the pipeline caps at 5000 files. |
| Search seems slow / 2 tests skip | ripgrep isn't on `PATH`; install it (step 5) or ignore — the fallback is correct, just slower. |
| `python` runs Python 2 | Use `python3` (and `python3 -m venv`). |
| Uploaded folder vanishes right after upload | You ran the backend with a bare `--reload`. Uploads are written under `./uploaded_repos/`, so uploading a Python project trips the reloader, restarts the server, and clears the in-memory registry. Use the `--reload-dir` command in step 6. |
| Port already in use | Change `--port` for uvicorn and/or run `next dev -p <port>`, and update `NEXT_PUBLIC_API_BASE_URL` / `CORS_ORIGINS` accordingly. |

---

## Next steps
- Architecture & data flow → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Security model & enforcement → [docs/SECURITY.md](docs/SECURITY.md)
- MCP server & clients → [docs/MCP.md](docs/MCP.md)
- Deployment guides → [docs/DEPLOY.md](docs/DEPLOY.md)
- What's deferred and why → [docs/ROADMAP.md](docs/ROADMAP.md)