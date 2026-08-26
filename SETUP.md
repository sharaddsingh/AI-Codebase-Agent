# Setup guide

A step-by-step walkthrough to get the **AI Codebase Engineering Agent** running
locally from scratch. For the architecture and the full env-var reference, see
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

If `python` maps to Python 2 on your system, use `python3` everywhere below.

---

## 2. Configure environment

From the repository root:

```bash
cp .env.example .env
```

Open `.env` and choose one of:

- **With a real model:** set `MODEL_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=sk-ant-...`
- **Without any key (recommended for a first run):** set `MODEL_PROVIDER=mock`

Everything else has working defaults. `.env` is git-ignored — never commit it.

---

## 3. Python backend, engine, agent, and MCP

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
uvicorn backend.main:app --reload --port 8000
```
Expect a JSON startup log line. If `ALLOWED_REPO_ROOTS` is empty you'll see a
one-line warning that registration is unrestricted — expected for local dev.

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
2. Register a repository by **absolute path**. Use the bundled fixture, e.g.
   `C:\Users\you\...\ai-codebase-agent\tests\fixtures\sample_repo`
   (or the repo root itself).
3. Browse the file tree and open a file in the viewer.
4. In the chat, ask: **"How does authentication work?"**
5. Watch the activity timeline (classify → plan → tool calls → answer) and the
   citation panel populate with clickable `file:line` references.

### Via curl (backend only)
```bash
# Health
curl http://localhost:8000/api/health

# Register a repo (returns JSON incl. its "id")
curl -X POST http://localhost:8000/api/repositories \
  -H "Content-Type: application/json" \
  -d '{"path": "tests/fixtures/sample_repo", "name": "sample"}'

# Ask the agent (SSE stream). Replace <REPO_ID> with the id from above.
curl -N -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"repo_id": "<REPO_ID>", "question": "How does authentication work?"}'
```

With `MODEL_PROVIDER=mock` the agent returns a deterministic scripted response —
useful to confirm the full request→stream path before wiring a real key.

---

## 8. Tests, lint, and type checks

**Python** (repo root, venv active):
```bash
python -m pytest
python -m ruff check .
python -m mypy code_intelligence retrieval agent backend
```
Expected: `95 passed, 2 skipped` (the 2 skips are ripgrep-specific and run only
when ripgrep is installed), ruff clean, mypy clean.

**Frontend** (from `frontend/`):
```bash
npm test
npm run lint
npm run build
```

---

## 9. (Optional) Docker

> ⚠️ The Docker files are **scaffolding and untested** in this environment
> (Docker was not available during development). Treat them as a starting point.

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY, or MODEL_PROVIDER=mock
CODE_DIR=/abs/path/to/your/code docker compose -f docker/docker-compose.yml up --build
```
Then open http://localhost:3000. Inside the container, register a repo by its
**in-container** path (e.g. `/repos/my-project`, the mounted `CODE_DIR`).

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Frontend loads but every call fails | Backend not running, or `NEXT_PUBLIC_API_BASE_URL` doesn't match the backend URL. Start the backend first. |
| CORS error in browser console | Add the frontend origin to `CORS_ORIGINS` in `.env` (default already allows `http://localhost:3000`). |
| Chat error "model not configured" | `MODEL_PROVIDER=anthropic` but `ANTHROPIC_API_KEY` is empty. Set the key, or switch to `MODEL_PROVIDER=mock`. |
| "Path is not within an allowed repository root" | `ALLOWED_REPO_ROOTS` is set and doesn't include your path. Add it, or clear the variable for local dev. |
| Register fails with "Path does not exist" | Use an **absolute** path to an existing directory. |
| Search seems slow / 2 tests skip | ripgrep isn't on `PATH`; install it (step 5) or ignore — the fallback is correct, just slower. |
| `python` runs Python 2 | Use `python3` (and `python3 -m venv`). |
| Port already in use | Change `--port` for uvicorn and/or run `next dev -p <port>`, and update `NEXT_PUBLIC_API_BASE_URL` / `CORS_ORIGINS` accordingly. |

---

## Next steps
- Architecture & data flow → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Security model & enforcement → [docs/SECURITY.md](docs/SECURITY.md)
- MCP server & clients → [docs/MCP.md](docs/MCP.md)
- What's deferred and why → [docs/ROADMAP.md](docs/ROADMAP.md)
