# MCP servers

The project speaks Model Context Protocol over **two** surfaces: the official
remote GitHub MCP server (read-only, browser workflow) and a standalone local
MCP server (optional, for external MCP clients such as Claude Desktop). Both
sides use the official `mcp` SDK — the protocol is not hand-rolled.

---

## 1. Remote GitHub MCP server (browser workflow)

GitHub repositories are read over the official remote MCP server at
`api.githubcopilot.com/mcp/readonly` via Streamable HTTP, authenticated with a
server-side PAT. The browser-side agent never clones the repo and never touches
the local filesystem for GitHub content.

```
Browser
   │
   ▼
FastAPI backend (registry.register_github)
   │
   ▼
code_intelligence/github_mcp_client.py
   │
   ▼
api.githubcopilot.com/mcp/readonly  (remote, read-only toolsets: repos, git)
   │
   ▼
GitHub
```

**Tools the agent actually uses through MCP:** `get_repository`, `get_file_contents`,
`search_code`, `list_commits`, and similar read-only MCP tools. All calls are
`POST` over Streamable HTTP with a single bearer header — the token never
appears in responses, citations, or logs.

**Read-only by construction.** The transport is configured with the `repos` and
`git` toolsets (no `issues`, `pull_requests`, etc.) and the client never opens
a write path. Removing a registered GitHub repo is a *local* forget; it does
not issue an MCP write.

**Bounded coverage.** If GitHub caps blob fetches mid-search, the registry
records `truncated=true` and a `notes` caveat. The agent cannot claim it
searched the whole repo when it did not.

See [SECURITY.md](SECURITY.md) for the token posture and the
`tests/test_api.py` GitHub cases (offline via a fake MCP server) for the
contract.

---

## 2. Standalone local MCP server (`mcp/server.py`)

For external MCP clients such as Claude Desktop, the project ships a separate
local MCP server that exposes the local-codebase engine over stdio using the
official `mcp` SDK.

> It reuses the exact same `code_intelligence` engine as the backend, so
> containment, ignore rules, binary / size refusal, and snapshots behave
> identically across both surfaces.

### Tools

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

### Security properties

- **Explicit scope + allow-list.** `repo_root` is resolved to a real path; if
  `MCP_ALLOWED_ROOTS` (OS-path-separator list) is set, any root outside it is
  refused with a `ToolError`.
- **Containment.** Individual file/dir paths are checked by the same
  `code_intelligence` engine the backend uses — traversal outside `repo_root`
  is impossible.
- **Clean errors.** Engine failures (bad path, binary, too large, …) surface
  as `ToolError` with a human-readable message, not a crash.
- **Untrusted content.** The server's instructions state that returned content
  is repository *data*, not instructions.

The `mcp/` directory is intentionally **not** a Python package (no
`__init__.py`), and the SDK is imported before the repo root is added to
`sys.path`, so the local directory can never shadow the installed `mcp` SDK.

### Run it

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

### Contract tests
`tests/test_mcp_contract.py` drives the server through the SDK's in-memory
`Client` (the same protocol a real client speaks) and asserts: the tool surface
is present, search + read work, ignored paths are excluded, snapshots are
returned, traversal is blocked, binary files are refused, and the allow-list
is enforced.

---

## 3. Relationship between the two surfaces

- The browser workflow goes through the **remote GitHub MCP** server for
  GitHub repos and a browser-supplied upload for local folders. The browser
  itself never opens an MCP connection.
- The standalone local MCP server is for *external* MCP clients that want to
  point the agent at a folder on the user's machine. It is independent of the
  FastAPI backend.
- Both surfaces reuse the same `code_intelligence` engine, so the safety and
  bound guarantees are consistent everywhere.