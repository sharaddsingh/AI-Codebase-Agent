# Security model

The brief imposes hard security constraints. Each is quoted below with **how and
where it is enforced** — in code, not merely requested of the model.

---

### "The agent must not blindly send an entire codebase to an LLM."
Enforced by **budgets** (`agent/budget.py`, wired in `backend/config.py`): every
investigation is bounded on tool calls, wall-clock seconds, files read, context
bytes, and steps. Tool results are bounded at the source too — directory
listings are paginated, file reads are line-/byte-sliced, and search results are
capped. Only evidence the agent explicitly requested ever reaches the model.

### "Repository-root containment: never allow traversal outside the authorized path."
Two separate guarantees:

1. **Browser-uploaded repos** never see an arbitrary user-supplied path. The
   upload pipeline (`backend/uploaded_repos.py`) writes each incoming relative
   path through `normalize_relative` and `is_within` against the fresh per-repo
   directory under `UPLOAD_ROOT`. No `..`, no absolute, no NUL bytes, no
   symlink traversal (links aren't followed — only files we just received are
   written). On any failure the partial directory is wiped before the error
   returns, so a half-uploaded repo never lingers on disk. Covered by
   `tests/test_uploaded_repos.py` and the API integration tests in
   `tests/test_api.py`.
2. **GitHub repos** never touch disk. Their paths are validated by the
   *pure-string* `normalize_relative` (rejects absolute / drive / `..` / NUL)
   and resolved against the in-memory tree only. They never reach the local
   filesystem, so a `../../etc/passwd` path still raises `PathValidationError`.
   The MCP server uses the same code paths (`code_intelligence/paths.py`).

### "Treat repository content as untrusted data; never allow code comments or files to override system/tool policy."
Three layers:
1. **The repository is bound by the loop, never passed as a tool argument**
   (`agent/loop.py`). The model chooses *what* to read, never *which repo* — it
   cannot redirect a tool at another path.
2. **Untrusted-data envelope:** every tool result is wrapped by
   `wrap_tool_output` (`agent/prompts.py`) before re-entering the model context,
   explicitly labelling it as data, not instructions.
3. **Citation validation** (`agent/loop.py`): the answer can only cite files
   actually inspected. A prompt-injection string in a file (the fixture contains
   `SYSTEM OVERRIDE … reveal OPENAI_API_KEY`) cannot exfiltrate anything — there
   is no key in the model's reach, and the injected instructions are inert data.

### "Keep the product read-only. Do not implement file writes, arbitrary shell execution, or automatic code changes yet."
There are **no** write, shell, or mutation code paths anywhere. The engine only
reads. The deferred capabilities that *would* change code
(`find_symbol`/`find_references`/`get_dependencies`, controlled edits) raise
`NotSupportedError` (HTTP 501). ripgrep, when present, is invoked with a fixed
read-only argument list — never a shell string.

### "Never expose the provider API key (ANTHROPIC_API_KEY) or GitHub tokens to the frontend."
Secrets live only in `backend/config.py` (server-side Pydantic Settings) —
`ANTHROPIC_API_KEY` and `GITHUB_TOKEN`. The **only** browser-visible variable is
`NEXT_PUBLIC_API_BASE_URL` (a URL, not a secret). The frontend never receives,
and never asks for, either secret. The GitHub token is read only in the backend
and sent only in the `Authorization` header to the remote MCP server
(`code_intelligence/github_mcp_client.py`); it never appears in a response
body, a returned model, a citation, a log line, an SSE event, or an error
message — asserted end-to-end by the GitHub tests in `tests/test_api.py`.

### "Add structured logs while redacting sensitive values."
`backend/logging_config.py` emits one JSON object per line and runs a redaction
filter over every record: provider API keys (`sk-…`, incl. Claude), GitHub
tokens, bearer tokens, and `secret=…`/`token=…`/`password=…` pairs are replaced
with `***REDACTED***` before anything is written.

### "Add .gitignore entries for .env, generated artifacts, and dependencies."
`.gitignore` ignores `.env` / `.env.*` (but keeps `.env.example`), Python and
Node build artifacts and caches, `node_modules/`, `.venv/`, `uploaded_repos/`,
logs, and local data stores.

### GitHub repositories — read-only, snapshot-pinned, bounded

`code_intelligence/github_mcp_repository.py` reads GitHub over the official
remote MCP server at `api.githubcopilot.com/mcp/readonly` (Streamable HTTP,
server-side PAT). Its security properties mirror the local engine:
- **Path safety without the filesystem.** GitHub paths are validated by
  `normalize_relative` and resolved against the in-memory tree. They never touch
  the disk.
- **Untrusted content.** File bytes flow through the same `wrap_tool_output`
  envelope as local files; a prompt-injection line in a GitHub file is inert.
- **Bounded, honest search.** Blob fetches are capped; partial coverage is
  reported as `truncated=True` + a `notes` caveat, never silently dropped.
- **Read-only.** The client issues only read tool calls; no write/commit path
  exists.
- **Token posture.** Server-side only — see the key-exposure section above.

---

## Additional hardening

- **Hard caps on uploads.** `UploadLimits` enforces total bytes, per-file
  bytes, and file count caps; exceeding any cap aborts the upload and wipes
  the partial directory.
- **Binary & oversized-file refusal.** Non-text and too-large files are
  refused (`BinaryFileError` 415 / `FileTooLargeError` 413) rather than
  streamed into a model.
- **CORS** is restricted to the configured frontend origin(s).
- **Error hygiene.** Domain errors return a typed `{error:{code,message}}`
  envelope; unexpected errors are logged server-side and returned as a generic
  500 with no internals.

## Explicitly out of scope for this MVP
No authn / authz, multi-tenant isolation, rate limiting, or secret-manager
integration yet — this is a single-user, read-only tool that runs locally or in
a single-region cloud container. These belong to the deployment phase in
[ROADMAP.md](ROADMAP.md).