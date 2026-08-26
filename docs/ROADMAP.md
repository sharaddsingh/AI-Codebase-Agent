# Roadmap (deferred phases)

This MVP implements Phases 0–3 (the local engine, the MCP server, the bounded
agent, and the frontend) **plus read-only GitHub repository support** (see
below). The remaining phases are **intentionally deferred**: documented and,
where useful, scaffolded with real interfaces that raise `NotSupportedError` —
**none of those are implemented, and the product does not pretend otherwise.**

Status legend: 🟢 implemented · 🟡 interface/placeholder exists · ⚪ documented only

---

## Repository capabilities

| Capability | Status | Where |
|-----------|--------|-------|
| `list_files`, `read_file`, `search_code`, `get_file_metadata`, `get_snapshot` — local | 🟢 | `code_intelligence/local_adapter.py` |
| `list_files`, `read_file`, `search_code`, `get_file_metadata`, `get_snapshot` — GitHub | 🟢 | `code_intelligence/github_adapter.py` |
| `find_symbol`, `find_references`, `get_dependencies` | 🟡 | `code_intelligence/repository.py` (raise `NotSupportedError`) |

## Phase: GitHub repositories — implemented
🟢 `GitHubRepositoryAdapter` (`code_intelligence/github_adapter.py`) reads a
public — or token-authorized — GitHub repo over the REST API, **read-only, no
clone**. At registration it resolves the default branch → commit sha and fetches
the recursive git tree once; the snapshot is pinned to that commit
(`snapshot.id = gh:<sha[:12]>`, `revision = <full sha>`). File contents are
fetched lazily per blob-sha and cached; whole-file reads above the size limit are
refused *without* downloading. Search reuses the **same lexical matcher** as local
over tree files fetched under a bounded budget (file-count / size / deadline);
when coverage is capped it returns `truncated=True` and a `notes` caveat, so the
agent never implies it searched the whole repository.

Decision vs. the original sketch: the external **GitHub-MCP proxy was dropped** in
favor of a scoped, in-process REST client (`code_intelligence/github_client.py`) —
simpler, fully offline-testable (`httpx.MockTransport`), no extra process. Auth is
an optional **server-side** `GITHUB_TOKEN` (raises rate limits / enables private
repos); it is never exposed to the browser, a response, a citation, a log, or an
error. See [SECURITY.md](SECURITY.md).

## Phase: Unified Local + GitHub layer — implemented
🟢 The registry (`code_intelligence/registry.py`) is the composition layer:
`register(source)` **auto-detects** whether `source` is a local path or a GitHub
URL — by URL *host*, not a substring test (`code_intelligence/github_url.py`) —
and routes to the matching adapter. Everything above the adapter (file/search
routers, the agent loop, prompts, tool dispatch, MCP) is source-agnostic and
needed no change. Local and GitHub repos coexist in one registry with distinct
ids; snapshot ids accommodate both (`git:` / `wt:` / `gh:`).

**Boundary this pass:** the standalone **MCP server stays local-only** — its tools
take a filesystem `repo_root`. It already goes through `RepositoryInterface` (the
local adapter) and does not regress; exposing GitHub repos over MCP is future work.

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
instead of lexical search **without changing its call sites**. Today retrieval
is purely lexical (`retrieval/lexical.py`, 🟢).

## Phase: Tree-sitter AST / code graph
⚪ Parse with Tree-sitter to build symbols, references, and an import/dependency
graph — the implementations behind `find_symbol` / `find_references` /
`get_dependencies`. Enables precise "where is this used" and change-impact
answers instead of lexical approximations.

## Phase: Controlled code changes
⚪ The product is **read-only today** by explicit requirement. A future,
carefully-gated capability would propose diffs (never silent writes) behind
review/approval. No write path exists in the current code.

## Phase: Infrastructure & operations
⚪ All documented targets, none enabled:
- **PostgreSQL** — persist repositories, snapshots, eval runs (registry is
  in-memory today).
- **Redis** — caching, rate limiting, job coordination.
- **Qdrant** — vector store for the Hybrid-RAG phase.
- **OpenTelemetry** — tracing/metrics across the agent loop and tools.
- **Eval harness** — scored, repeatable agent evaluations.
- **Cloud deployment** — plus authn/authz, multi-tenant isolation, secret
  management (see [SECURITY.md](SECURITY.md) "out of scope").

The `docker/docker-compose.yml` file lists Postgres/Redis/Qdrant as **commented,
disabled** services so they are never mistaken for working features.

---

### Design guarantees that make the above additive
- One `RepositoryInterface`; adapters are swappable.
- Retrieval is accessed through an interface, so lexical → hybrid is a swap.
- Snapshot ids tie evidence and (future) indexes to a specific code state.
- The model provider is an adapter (`AnthropicAdapter`/Claude today), so changing
  models or vendors is isolated.
