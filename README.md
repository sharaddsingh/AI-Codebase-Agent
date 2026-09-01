# AI Codebase Agent

A web-based, read-only AI agent that investigates codebases and answers questions with file and line citations. Two ways to bring your code: **upload a folder from your browser**, or **point it at a public GitHub repo**. That's it — no path-input, no server-side filesystem permissions, no shared mounts.

Instead of sending an entire codebase to an LLM, the agent plans an investigation, searches for relevant evidence, reads only the files it needs, evaluates what it found, and produces a cited answer. Everything is bounded: tool calls, time, files read, and steps.

---

## Highlights

- **Browser folder upload** — pick or drop a folder; the browser streams it straight to the backend. No filesystem access for the server beyond what you sent it.
- **GitHub via official MCP** — paste a `https://github.com/owner/repo` URL and the agent reads it over the read-only remote GitHub MCP server. No clones.
- **Plan → Act → Observe → Answer** with strict execution budgets.
- **Cited answers** — every claim links back to a file and line range, with one click to jump there.
- **Modern UI** — animated header orb, repository cards with 3D hover tilt, drag-drop upload modal, citation beams across the highlighted line, and a vertical activity rail.

---

## Quick start

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm

### 1. Clone and install

```bash
git clone https://github.com/example/ai-codebase-agent.git
cd ai-codebase-agent
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt   # tests + linters
cd frontend && npm install && cd ..
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`. Three ways to wire a model:

**Anthropic Claude (default)** — uses Anthropic's native Messages API:

```env
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...           # required for GitHub repos via MCP
```

**Any OpenAI-compatible host** (TaBiToken, OpenRouter, llama.cpp + shim, vLLM, Ollama, ...). The agent loop already produces OpenAI-style messages and tool schemas, so this is mostly a passthrough:

```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://your-host.example   # no trailing /v1
OPENAI_MODEL=your-model-name
```

**`MODEL_PROVIDER=mock`** runs without any API key and gives you a deterministic scripted agent for demos.

> **Anthropic-only base_url:** `ANTHROPIC_BASE_URL` only works with hosts that speak Anthropic's native Messages API. Most third-party gateways are OpenAI-compatible — if you see `<!DOCTYPE html>` or `PermissionDeniedError` with HTML in the error message, switch to `MODEL_PROVIDER=openai` and use `OPENAI_BASE_URL` against the same host.

### 3. Run

Two terminals:

```bash
# Terminal 1: backend (http://localhost:8000)
# The --reload-dir flags keep the watcher off ./uploaded_repos/ — otherwise
# uploading a Python project restarts the server and clears the registry.
python -m uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --reload-dir retrieval --reload-dir code_intelligence --port 8000

# Terminal 2: frontend (http://localhost:3000)
cd frontend
npm run dev
```

Open `http://localhost:3000`. Click **Upload** to drop a folder, or click **GitHub** and paste a URL like `facebook/react`.

---

## How to use

1. Add a repo: drop a folder into the upload modal, or paste a GitHub URL in the GitHub form.
2. Browse the file tree in the left rail.
3. Open a file, or click a citation in an answer to jump to the cited line.
4. Ask a question in the chat panel:

   ```text
   How does authentication work?
   Where is theme switching implemented?
   Why might this endpoint return 401?
   ```

5. Watch the activity rail on the right as the agent investigates.
6. Click any citation chip to open the cited file/line range with a beam-flash highlight.

---

## Architecture

```
                    Browser (Next.js + WebGL)
                              |
                              v
                       FastAPI Backend
                              |
                              v
                  Repository Registry
                       /           \
                      v             v
        Upload Pipeline          GitHub MCP Client
             |                          |
             v                          v
      Local Filesystem         Remote GitHub MCP Server
       (uploaded_repos/)        (api.githubcopilot.com)
                                          |
                                          v
                                       GitHub
```

- **Upload pipeline** — every file is written to `./uploaded_repos/<repo_id>/` after containment + size + ignore-dir checks. The directory is wiped when the repo is removed.
- **GitHub MCP** — the official remote MCP server at `api.githubcopilot.com/mcp/readonly` over Streamable HTTP, authenticated with a server-side PAT. The token never reaches the browser.

---

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_PROVIDER` | `anthropic` | `anthropic` (Claude Messages API), `openai` (any OpenAI-compatible host), or `mock` |
| `ANTHROPIC_API_KEY` | — | Server-side model credential |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Model identifier |
| `ANTHROPIC_MAX_TOKENS` | `4096` | Cap on each model response |
| `ANTHROPIC_BASE_URL` | — | Override the Anthropic API base URL (Anthropic-protocol hosts only) |
| `OPENAI_API_KEY` | — | Required when `MODEL_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model identifier when `MODEL_PROVIDER=openai` |
| `OPENAI_BASE_URL` | — | Override for OpenAI-compatible hosts (e.g. TaBiToken, OpenRouter, llama.cpp + shim) |
| `OPENAI_MAX_TOKENS` | `4096` | Cap on each model response when `MODEL_PROVIDER=openai` |
| `AGENT_MAX_TOOL_CALLS` | `20` | Bound on tool calls per question |
| `AGENT_MAX_SECONDS` | `150` | Bound on total investigation time |
| `AGENT_MAX_FILES` | `20` | Bound on files read |
| `AGENT_MAX_CONTEXT_BYTES` | `300000` | Bound on context bytes |
| `AGENT_MAX_STEPS` | `24` | Bound on agent loop iterations |
| `UPLOAD_ROOT` | `./uploaded_repos` | Where browser-uploaded folders land |
| `GITHUB_TOKEN` | — | Required for the GitHub MCP integration |
| `GITHUB_MCP_URL` | `https://api.githubcopilot.com/mcp/readonly` | GitHub MCP server endpoint |
| `LOG_LEVEL` | `INFO` | Backend logging level |
| `CORS_ORIGINS` | `http://localhost:3000` | Frontend origins allowed by CORS |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Where the browser reaches the backend |

`GITHUB_TOKEN` is required for GitHub repositories — the official MCP server mandates it even for public repos.

---

## Deployment

The backend is a single FastAPI process; the frontend is a Next.js static build that the backend can serve. Three deployment targets are supported:

### Single Docker image

```bash
docker build -t ai-codebase-agent .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY \
  -e GITHUB_TOKEN \
  -v ai-codebase-agent-uploads:/app/uploaded_repos \
  ai-codebase-agent
```

The image boots uvicorn and serves the prebuilt frontend at the same origin. Persistent volume for `UPLOAD_ROOT` is required for uploads to survive restarts.

### Render

Click the deploy button or use the included `render.yaml` Blueprint. Set `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` in the dashboard's environment group.

### Fly.io

`fly launch --copy-config` then `fly deploy`. The included `fly.toml` sets up a single-region app with a 1 GB persistent volume for uploads.

See [docs/DEPLOY.md](docs/DEPLOY.md) for the full guide.

---

## Testing

```bash
# Backend
python -m pytest
python -m ruff check .

# Frontend
cd frontend
npx tsc --noEmit
npm run lint
```

---

## Security

- Every upload is contained inside `UPLOAD_ROOT` with strict per-path validation (no `..`, no absolute, no symlinks, ignore-dir deny-list for `.git`, `node_modules`, build output).
- Hard caps on total bytes, per-file bytes, and file count per upload.
- Removing an uploaded repo wipes its on-disk directory.
- GitHub integration is read-only over the MCP — the backend cannot mutate the remote.
- All secrets (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`) live only in server env vars and never appear in responses, citations, logs, or errors.
- Repository content is treated as untrusted input; the agent's renderer never executes HTML.

See [docs/SECURITY.md](docs/SECURITY.md) for the full threat model.

---

## Project structure

```
ai-codebase-agent/
  backend/            FastAPI app, routers, schemas, config, deps
  code_intelligence/  Repository abstraction (local + GitHub), registry
  retrieval/          Lexical search engine (ripgrep / pure-python)
  agent/              Bounded agent loop, tools, budgets
  mcp/                Standalone MCP server for repo tools
  frontend/           Next.js 14 + TypeScript + Tailwind
  tests/              pytest suite (repos are built in tmp dirs, no checked-in fixtures)
  docs/               Architecture, security, deployment, MCP
  Dockerfile          Multi-stage build (frontend + backend)
  render.yaml         Render Blueprint
  fly.toml            Fly.io app manifest
```

---

## License

See [LICENSE](LICENSE).