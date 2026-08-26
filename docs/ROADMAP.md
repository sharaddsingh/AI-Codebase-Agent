# Roadmap (deferred phases)

This MVP implements Phases 0–3: the local engine, the MCP server, the bounded
agent, and the frontend. Everything below is **intentionally deferred**. It is
documented and, where useful, scaffolded with real interfaces that raise
`NotSupportedError` — **none of it is implemented, and the product does not
pretend otherwise.**

Status legend: 🟢 implemented · 🟡 interface/placeholder exists · ⚪ documented only

---

## Repository capabilities

| Capability | Status | Where |
|-----------|--------|-------|
| `list_files`, `read_file`, `search_code`, `get_file_metadata`, `get_snapshot` | 🟢 | `code_intelligence/local_adapter.py` |
| `find_symbol`, `find_references`, `get_dependencies` | 🟡 | `code_intelligence/repository.py` (raise `NotSupportedError`) |

## Phase: GitHub repositories
⚪ / 🟡 `GitHubRepositoryAdapter` is a documented, non-functional placeholder
(`code_intelligence/github_adapter.py`). The plan is to back it with an external
**GitHub MCP** server rather than hand-rolling API calls. Because the agent only
knows `RepositoryInterface`, this is an additive adapter — no call-site changes.

## Phase: Unified Local + GitHub layer
⚪ A composition layer that presents local repos and GitHub repos through the one
interface, selecting the adapter (and, for GitHub, the MCP client) by repository
kind. Snapshot ids already accommodate both (`git:` / `wt:`).

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
