# MCP server

`mcp/server.py` exposes the local codebase engine as **Model Context Protocol**
tools using the **official MCP Python SDK** (`mcp` package) — the protocol is not
hand-rolled. Any MCP-capable client (Claude Desktop, the MCP inspector, another
agent) can connect over stdio and traverse a *local* repository safely.

> The MCP server reuses the exact same `code_intelligence` engine as the backend,
> so containment, ignore rules, binary/size refusal, and snapshots behave
> identically across both surfaces.

---

## Tools

Every tool takes an explicit `repo_root` (absolute path). There is no ambient
"current repository" — scope is passed on every call and authorized per call.

| Tool | Purpose | Key arguments |
|------|---------|---------------|
| `list_files` | List a directory's entries (ignore-aware, paginated) | `repo_root`, `path=""`, `page`, `page_size` |
| `read_file` | Read a bounded slice of a text file | `repo_root`, `path`, `start_line`, `end_line`, `max_bytes` |
| `search_code` | Lexical / regex search across the repo | `repo_root`, `query`, `regex`, `case_sensitive`, `path_glob`, `max_results` |
| `get_file_metadata` | Size, line count, language, binary flag, hash | `repo_root`, `path` |
| `get_repository_snapshot` | Resolved root, stable id, snapshot (git/content) | `repo_root` |

All tools are **read-only**. Argument schemas are derived and validated by the
SDK from the typed function signatures.

## Security properties (enforced across the MCP boundary)

- **Explicit scope + allow-list.** `repo_root` is resolved to a real path; if
  `MCP_ALLOWED_ROOTS` (OS-path-separator list) is set, any root outside it is
  refused with a `ToolError`.
- **Containment.** Individual file/dir paths are checked by the same
  `code_intelligence` engine the backend uses — traversal outside `repo_root`
  is impossible.
- **Clean errors.** Engine failures (bad path, binary, too large, …) surface as
  `ToolError` with a human-readable message, not a crash.
- **Untrusted content.** The server's instructions state that returned content
  is repository *data*, not instructions.

The `mcp/` directory is intentionally **not** a Python package (no
`__init__.py`), and the SDK is imported before the repo root is added to
`sys.path`, so the local directory can never shadow the installed `mcp` SDK.

---

## Run it

```bash
python mcp/server.py
```

Restrict which roots it may serve:

```bash
# POSIX (":" separator)
MCP_ALLOWED_ROOTS=/home/me/code python mcp/server.py
# Windows (";" separator)
set MCP_ALLOWED_ROOTS=C:\code&& python mcp/server.py
```

### Connect from Claude Desktop (example)
Add to the client's MCP config (adjust the absolute path):

```json
{
  "mcpServers": {
    "codebase-local": {
      "command": "python",
      "args": ["C:/Users/you/ai-codebase-agent/mcp/server.py"],
      "env": { "MCP_ALLOWED_ROOTS": "C:/Users/you/code" }
    }
  }
}
```

## Contract tests
`tests/test_mcp_contract.py` drives the server through the SDK's in-memory
`Client` (the same protocol a real client speaks) and asserts: the tool surface
is present, search+read work, ignored paths are excluded, snapshots are
returned, traversal is blocked, binary files are refused, and the allow-list is
enforced.

## Relationship to the backend
The FastAPI backend does **not** proxy through this MCP server today — both call
the same engine directly. The MCP server is a first-class, independently usable
protocol surface. It is **local-only** this pass: its tools take a filesystem
`repo_root`. The Local + GitHub unification already lives in the registry on the
API side; exposing GitHub repos over MCP — or composing an external **GitHub MCP**
server behind the same `RepositoryInterface` — remains future work (see
[ROADMAP.md](ROADMAP.md)).
