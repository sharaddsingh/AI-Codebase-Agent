# Architecture

The AI Codebase Agent is a **read-only, tool-using agent** that investigates a
software repository and answers questions with **file/line citations**. This
document describes the current implementation and where the seams for future
phases sit.

---

## 1. The one abstraction: `RepositoryInterface`

Everything above the storage layer — the API, the agent loop, the MCP server —
programs against a single interface and never contains `if local / else github`
branching.

```
                 ┌─────────────────────────────┐
   agent loop ──▶│                             │
   API routers──▶│     RepositoryInterface     │  (code_intelligence/repository.py)
   MCP server ──▶│                             │
                 └───────────────┬─────────────┘
                                 │  implemented by
                 ┌───────────────┴──────────────────────────────┐
                 ▼                                              ▼
   LocalRepositoryAdapter                      GitHubMCPRepository
   code_intelligence/local_adapter.py          code_intelligence/github_mcp_repository.py
   (used for browser uploads)
```

**Implemented capabilities** (every adapter must provide them): `get_snapshot`,
`list_files`, `read_file`, `search_code`, `get_file_metadata`.

**Deferred capabilities** (concrete methods that raise `NotSupportedError`):
`find_symbol`, `find_references`, `get_dependencies`. These define the target
for the code-graph phase.

---

## 2. Two ways to register a repository

The registry exposes **two** explicit entry points. There is no implicit
source detection and no path-input endpoint.

### a. Browser folder upload
```
Browser (showDirectoryPicker or drag-drop)
    └─▶ POST /api/repositories/upload (multipart, one part per file)
            └─▶ backend.uploaded_repos.save_upload
                    • normalize + contain each relative path
                    • enforce size, count, per-file, ignore-dir caps
                    • write into UPLOAD_ROOT/<repo_id>/
            └─▶ registry.register_uploaded(repo_dir)
                    • idempotent id = up_<sha256(repo_dir)[:12]>
                    • wraps in LocalRepositoryAdapter
            ◀── 201 RepositoryInfo
```

### b. GitHub URL
```
Browser (GitHub form)
    └─▶ POST /api/repositories/github {url}
            └─▶ parse_github_url (validates + canonicalizes)
            └─▶ registry.register_github(url)
                    • idempotent id = repo_<sha256("github:owner/repo")[:10]>
                    • opens GitHub MCP client (lazy), wraps in GitHubMCPRepository
            ◀── 201 RepositoryInfo
```

Both paths return the same `RepositoryInfo` shape, so the rest of the stack is
agnostic to how a repo got there.

---

## 3. Monorepo layout

```
code_intelligence/   Local repo engine: paths, ignore rules, list/read/search/metadata,
                     snapshots, the RepositoryInterface, the in-memory registry,
                     the GitHub MCP client + adapter, and the GitHub URL parser.
retrieval/           Lexical search (functional) + the deferred Hybrid-RAG scaffold.
agent/               Provider-agnostic model adapter, task classifier, tool specs,
                     the bounded agentic loop, budgets, prompts, typed events/results.
backend/             FastAPI app: config, structured logging, DI, routers
                     (health, repositories, files, search, agent SSE).
mcp/                 Standalone MCP server (official SDK) exposing the same read-only
                     tools over the Model Context Protocol.
frontend/            Next.js 14 (App Router) + TS + Tailwind: animated header orb,
                     RepoPanel with two + tiles (Upload + GitHub), drag-drop
                     upload modal, file tree, code viewer with citation beam,
                     chat panel with vertical activity rail, citation chips.
tests/               pytest suite: containment, ignore, engine, search, adapter,
                     registry, classifier, agent loop, MCP contract, API integration.
docs/                This directory.
Dockerfile, render.yaml, fly.toml  Single-image, single-region deploys.
```

---

## 4. Request / data flow

### Browsing (synchronous JSON)
```
Browser ──GET /api/repositories/{id}/tree|file|metadata|search──▶ FastAPI router
        ──▶ RepositoryRegistry.get(id) ──▶ adapter ──▶ engine
        ◀── bounded JSON (paginated listings, line-sliced files, capped matches)
```

### Asking a question (streamed)
```
Browser ──POST /api/agent/chat {repo_id, question}──▶ agent router
        ◀── text/event-stream of AgentEvents (SSE-over-POST):
            classified → plan → (status → tool_call → tool_result)* → answer → done
```

`EventSource` cannot issue POSTs, so the frontend uses `fetch` + a hand-written
SSE parser over the `ReadableStream` body (`frontend/lib/sse.ts`). The parser is
split into pure pieces and unit-tested without a network.

---

## 5. The bounded agentic loop (`agent/loop.py`)

This is the "plan → act → observe → evaluate → continue-or-answer" cycle,
made concrete and **bounded**:

1. **Classify** the task with a zero-token heuristic (`how_it_works`,
   `find_usages`, `debug`, `change_impact`, `general`) and emit a **plan**.
2. **Gather loop:** call the model with the tool schemas; for each tool call it
   requests, execute it against the bound repository, wrap the result as
   untrusted data, feed it back, and repeat.
3. **Budget check every iteration.** If any budget trips, stop gathering and
   **force a single final answer** with tools disabled — the agent always
   answers from evidence in hand rather than looping forever.
4. **Validate citations.** `path:line` / `path:start-end` references in the
   answer are kept only if that path was actually inspected and the line numbers
   are plausible (clamped to the file's real length). The model cannot cite what
   it never read.

Every step is emitted as an `AgentEvent` and streamed to the UI.

### Budgets (`agent/budget.py`)
Five simultaneous bounds — `max_tool_calls`, `max_seconds`, `max_files_read`,
`max_context_bytes`, `max_steps` — all configurable via env. They are the
concrete mechanism behind *"the agent must not blindly send an entire codebase
to an LLM."*

### Provider-agnostic model (`agent/model_adapter.py`)
`ModelAdapter` is the interface; `AnthropicAdapter` (Claude) is the provider and
`MockAdapter` (scripted responses) lets the entire stack run and be tested with
**no API key**. The internal message format is an OpenAI-style chat schema that
each adapter translates to its provider — `AnthropicAdapter` maps it onto
Claude's `tool_use`/`tool_result` blocks; swapping providers is one adapter.

---

## 6. Snapshot identity (`code_intelligence`)

Every repository resolves to a `RepoSnapshot` id:
- `git:<sha12>` (or `git:<sha12>+dirty`) when the root is a git work tree, else
- `wt:<hash>` derived from file metadata.

Citations carry the snapshot id, so an answer is tied to a specific code state —
the hook the future versioning / indexing phases build on.

---

## 7. Configuration & DI (`backend/config.py`, `backend/deps.py`)

All config comes from environment variables / `.env` (Pydantic Settings) and is
read **server-side only**. Process-wide singletons (the registry, the model
adapter) are created lazily and can be overridden in tests (e.g. injecting
`MockAdapter`). See [SECURITY.md](SECURITY.md) for the secret-handling rules
and [MCP.md](MCP.md) for the protocol server.