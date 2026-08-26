# AI Codebase Engineering Agent

A web-based, **read-only** AI agent that investigates a software repository using
tools and answers questions with **file/line citations**. It plans, calls
read-only tools against a local codebase, observes the results, and either keeps
digging or answers — all under strict budgets, and never sending a whole
codebase to a model.

This is a working **local-repository MVP (Phases 0–3)** with clean, documented
interfaces for later phases. It does **not** pretend future capabilities exist.

### The four responsibilities it demonstrates
1. **AI coding agent** — a bounded plan→act→observe→answer loop with cited answers.
2. **Full-stack** — FastAPI (Python) backend + Next.js (TypeScript) frontend.
3. **Agentic workflow** — task classification, tool calls, observation,
   budget-aware evaluation, forced finalization, citation validation.
4. **MCP & retrieval-based traversal** — an official-SDK MCP server plus a
   lexical retrieval engine (with a documented Hybrid-RAG upgrade path).

---

## Repository layout

```
code_intelligence/  Local repo engine + RepositoryInterface + registry
retrieval/          Lexical search (+ deferred Hybrid-RAG interfaces)
agent/              Model adapter, classifier, tools, bounded loop, budgets
backend/            FastAPI app (health, repositories, files, search, agent SSE)
mcp/                Standalone MCP server (official SDK)
frontend/           Next.js 14 UI (tree, code viewer, chat, activity, citations)
tests/              pytest suite (97 tests) + fixture repository
docs/               ARCHITECTURE · SECURITY · MCP · ROADMAP
docker/             Dockerfiles + compose (scaffolding — see Limitations)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

---

## Prerequisites
- **Python 3.10+** (developed on 3.13)
- **Node.js 18+** (developed on 22) and npm
- Optional: **ripgrep** on `PATH` for fast search (a pure-Python fallback is used
  automatically if it is absent)
- An **Anthropic (Claude) API key** — *or* run with `MODEL_PROVIDER=mock` and no key at all

---

## Setup

```bash
# 1. From the repo root, configure environment
cp .env.example .env          # then edit .env (add ANTHROPIC_API_KEY, or set MODEL_PROVIDER=mock)

# 2. Python backend + engine + agent + MCP
python -m venv .venv
# Windows:            .venv\Scripts\activate
# macOS/Linux:        source .venv/bin/activate
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # + tests, ruff, mypy

# 3. Frontend
cd frontend && npm install && cd ..
```

---

## Run

Use three terminals (backend, frontend, and optionally the MCP server).

**Backend API** (http://localhost:8000, docs at `/docs`):
```bash
uvicorn backend.main:app --reload --port 8000
```

**Frontend** (http://localhost:3000):
```bash
cd frontend && npm run dev
```

**MCP server** (stdio; only needed to connect an external MCP client):
```bash
python mcp/server.py
```

Then open **http://localhost:3000**, register a repository by its absolute path
(try the bundled `tests/fixtures/sample_repo`), browse the tree, and ask the chat
a question like *"How does authentication work?"* — answers arrive with clickable
citations and a live activity timeline.

> No API key? Set `MODEL_PROVIDER=mock` in `.env` to exercise the full UI and API
> with a deterministic scripted agent.

---

## Tests, lint, type checks

**Python** (from repo root, venv active):
```bash
python -m pytest                                            # 95 passed, 2 skipped*
python -m ruff check .                                      # lint
python -m mypy code_intelligence retrieval agent backend    # types
```
\* the 2 skips are ripgrep-specific tests; they run when ripgrep is on `PATH`.

**Frontend** (from `frontend/`):
```bash
npm test          # vitest unit tests
npm run lint      # eslint
npm run build     # production build (also type-checks)
```

---

## Environment variables

All server-side; only `NEXT_PUBLIC_API_BASE_URL` reaches the browser. See
[.env.example](.env.example) for the full annotated list.

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_PROVIDER` | `anthropic` | `anthropic` (real model) or `mock` (no key) |
| `ANTHROPIC_API_KEY` | — | **Secret.** Required when provider is `anthropic` |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Claude model name |
| `ANTHROPIC_MAX_TOKENS` | `4096` | Max tokens per model response |
| `ANTHROPIC_BASE_URL` | — | Override the Anthropic API base URL |
| `AGENT_MAX_TOOL_CALLS` | `12` | Budget: tool calls per question |
| `AGENT_MAX_SECONDS` | `90` | Budget: wall-clock seconds |
| `AGENT_MAX_FILES` | `20` | Budget: files read |
| `AGENT_MAX_CONTEXT_BYTES` | `200000` | Budget: tool-output bytes fed to model |
| `AGENT_MAX_STEPS` | `16` | Budget: loop iterations |
| `ALLOWED_REPO_ROOTS` | *(empty)* | Path-separated allow-list; empty = unrestricted (dev) |
| `RESPECT_GITIGNORE` | `true` | Honor the repo's root `.gitignore` |
| `DEFAULT_REPO_PATH` | *(empty)* | Optional repo auto-registered at startup |
| `LOG_LEVEL` | `INFO` | Log level |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Where the browser calls the backend |
| `MCP_ALLOWED_ROOTS` | *(empty)* | Allow-list for the standalone MCP server |

---

## Security at a glance

Read-only throughout; repository content is treated as **untrusted data**;
repository-root **containment** with symlink resolution; **budgets** so no whole
codebase is ever sent to a model; **citation validation** so the agent can only
cite what it actually read; secrets are **server-side only** and **redacted from
logs**. Full details and enforcement points: [docs/SECURITY.md](docs/SECURITY.md).

---

## What's intentionally deferred

GitHub repositories (documented placeholder adapter), a unified Local+GitHub
layer, Hybrid RAG (embeddings + reranking), Tree-sitter AST/code-graph
(`find_symbol`/`find_references`/`get_dependencies`), controlled code changes,
and infrastructure (PostgreSQL, Redis, Qdrant, OpenTelemetry, eval harness, cloud
deploy). Each has a real interface or is clearly marked not-implemented — see
[docs/ROADMAP.md](docs/ROADMAP.md).

## Limitations / known blockers
- **Docker files are untested here.** Docker is not installed in the development
  environment, so `docker/` is provided as scaffolding, not verified images.
- **In-memory registry.** Registered repositories do not survive a backend
  restart (persistence is a deferred phase).
- **Lexical search only.** No semantic/embedding retrieval yet.
- **ripgrep optional.** Without it, search uses a slower pure-Python fallback and
  2 ripgrep-specific tests skip.
