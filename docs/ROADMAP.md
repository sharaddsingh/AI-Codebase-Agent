# Roadmap (deferred phases)

This release implements the **read-only local engine, the bounded agent, the
remote GitHub MCP integration, the browser upload pipeline, the modernized
UI, and the single-image deployment story**. The remaining phases are
intentionally deferred: documented and, where useful, scaffolded with real
interfaces that raise `NotSupportedError` — none of those are implemented, and
the product does not pretend otherwise.

Status legend: 🟢 implemented · 🟡 interface / placeholder exists · ⚪ documented only

---

## Repository registration

| Capability | Status | Where |
|-----------|--------|-------|
| **Browser folder upload** — multipart, contain + cap, register | 🟢 | `backend/routers/repositories.py`, `backend/uploaded_repos.py`, `code_intelligence/registry.register_uploaded` |
| **GitHub via official MCP** — read-only, snapshot-pinned | 🟢 | `code_intelligence/github_mcp_client.py`, `code_intelligence/github_mcp_repository.py`, `code_intelligence/registry.register_github` |
| Path-input registration | ❌ removed | — |
| `MCP_ALLOWED_ROOTS`-style local allow-list | ❌ removed (replaced by upload containment) | — |

## Repository capabilities

| Capability | Status | Where |
|-----------|--------|-------|
| `list_files`, `read_file`, `search_code`, `get_file_metadata`, `get_snapshot` — local | 🟢 | `code_intelligence/local_adapter.py` |
| `list_files`, `read_file`, `search_code`, `get_file_metadata`, `get_snapshot` — GitHub | 🟢 | `code_intelligence/github_mcp_repository.py` |
| `find_symbol`, `find_references`, `get_dependencies` | 🟡 | `code_intelligence/repository.py` (raise `NotSupportedError`) |

## Phase: GitHub repositories — implemented via the official MCP

🟢 GitHub repositories are read over the **official remote GitHub MCP server**
(`api.githubcopilot.com/mcp/readonly`, Streamable HTTP, server-side PAT). At
registration it resolves the default branch → commit sha and caches the
recursive tree once; the snapshot is pinned to that commit. File contents and
search reuse the same lexical matcher as local over tree files fetched under
a bounded budget (file count / size / deadline). When coverage is capped, the
response carries `truncated=true` and a `notes` caveat so the agent never
implies it searched the whole repository.

Auth is a **required** server-side `GITHUB_TOKEN`. It is never exposed to the
browser, a response, a citation, a log, or an error — see [SECURITY.md](SECURITY.md).

## Phase: Unified Local + GitHub layer — implemented

🟢 The registry (`code_intelligence/registry.py`) is the composition layer.
`register_uploaded(repo_dir)` and `register_github(url)` are explicit — there
is no auto-detection and no path-input endpoint. Everything above the adapter
(file / search routers, the agent loop, prompts, tool dispatch, MCP) is
source-agnostic and needed no change. Local and GitHub repos coexist in one
registry with distinct id prefixes (`up_…` vs `repo_…`); snapshot ids
accommodate both (`git:` / `wt:` / `gh:`).

## Phase: Hybrid RAG

🟡 Interfaces exist in `retrieval/base.py`:
`EmbeddingRetriever`, `Reranker`, `HybridRetriever` (all deferred). Target
pipeline:

```
lexical search ─┐
vector search  ─┼─▶ fuse / dedupe ─▶ rerank ─▶ ranked snippets
symbol search  ─┘
```

Planned vector store: **Qdrant**, chunked per snapshot so vectors invalidate
when the snapshot id changes. The agent will call `HybridRetriever.retrieve`
instead of lexical search without changing its call sites. Today retrieval is
purely lexical (`retrieval/lexical.py`, 🟢).

## Phase: Tree-sitter AST / code graph

⚪ Parse with Tree-sitter to build symbols, references, and an import /
dependency graph — the implementations behind `find_symbol` /
`find_references` / `get_dependencies`. Enables precise "where is this used"
and change-impact answers instead of lexical approximations.

## Phase: Controlled code changes

⚪ The product is **read-only today** by explicit requirement. A future,
carefully-gated capability would propose diffs (never silent writes) behind
review / approval. No write path exists in the current code.

## Phase: Infrastructure & operations

⚪ All documented targets, none enabled in the open-source release:
- **PostgreSQL** — persist repositories, snapshots, eval runs (registry is
  in-memory today).
- **Redis** — caching, rate limiting, job coordination.
- **Qdrant** — vector store for the Hybrid-RAG phase.
- **OpenTelemetry** — tracing / metrics across the agent loop and tools.
- **Eval harness** — scored, repeatable agent evaluations.
- **Cloud auth** — authn / authz, multi-tenant isolation, secret management
  (see [SECURITY.md](SECURITY.md) "out of scope").

---

### Design guarantees that make the above additive

- One `RepositoryInterface`; adapters are swappable.
- Registration goes through **explicit** entry points (`register_uploaded`,
  `register_github`), never auto-detection.
- Retrieval is accessed through an interface, so lexical → hybrid is a swap.
- Snapshot ids tie evidence and (future) indexes to a specific code state.
- The model provider is an adapter (`AnthropicAdapter` / Claude today), so
  changing models or vendors is isolated.
- A single `Dockerfile` (plus Render / Fly manifests) means deployment targets
  are interchangeable.