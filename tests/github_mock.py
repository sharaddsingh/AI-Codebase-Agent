"""In-process fake GitHub MCP client for tests (no network, no real MCP).

:func:`mock_client` returns an object that is a **drop-in replacement** for
:class:`code_intelligence.github_mcp_client.GitHubMCPClient` wherever the
registry injects ``github_client=``: it exposes the same blocking surface the
registry and the GitHub adapter actually use —

* ``connect()``     — called by ``RepositoryRegistry._get_github_client``
* ``close()``       — called by ``RepositoryRegistry.close_github_mcp``
* ``list_tools()``  — parity with the real client (not exercised by the adapter)
* ``call_tool(name, arguments=None, *, timeout=None) -> MCPToolResult``
                      — the one method ``GitHubMCPRepository`` drives, for the
                      four read tools ``list_commits``, ``get_repository_tree``,
                      ``get_file_contents`` and ``search_code``.

The adapter treats each tool result exactly as it would a real one: data tools
are consumed via :meth:`MCPToolResult.json`, so we hand back a single
``TextContent`` whose ``text`` is the JSON payload; ``get_file_contents`` is
consumed by inspecting the content blocks, so we hand back a single
``TextContent`` carrying the raw file bytes as UTF-8 text (the same shape the
adapter's ``_content_from_result`` decodes for an inlined text file).

The canned repository (any ``owner``/``repo``, e.g. ``octocat/hello``) is small
but shaped to satisfy the suite: a pinned head commit, a recursive tree that
includes an ``app/`` package and an ignored ``node_modules/`` entry, an
``app/security.py`` whose first lines contain ``verify_token``, and a
``search_code`` hit for that symbol. Passing ``repo_status=404`` makes
``list_commits`` return no commits, which drives the adapter's real
"repository not found" path without any network.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.types import TextContent

from code_intelligence.github_mcp_client import MCPToolResult

# Read tools the real server advertises and the adapter depends on. Exposed via
# ``list_tools`` purely for drop-in parity with GitHubMCPClient.
_READ_TOOLS: tuple[str, ...] = (
    "list_commits",
    "get_repository_tree",
    "get_file_contents",
    "search_code",
)

# A deterministic 40-hex head sha; the adapter pins the snapshot to sha[:12],
# yielding an id of the form ``gh:<12 hex>`` the tests assert on.
_HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
_HEAD_DATE = "2024-05-01T12:00:00Z"

# The file the scripted agent + the file/search tests read. ``verify_token``
# must appear within the first four lines (the tests slice lines 1-4).
_SECURITY_PY = '''\
"""Access-token verification for the sample GitHub fixture repo."""

def verify_token(token: str | None):
    """Return the authenticated user, or raise HTTP 401 on any failure."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    if token.count(".") != 2:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return {"user": "octocat"}
'''

_MAIN_PY = '''\
"""Tiny FastAPI-style entrypoint for the GitHub fixture repo."""

from .security import verify_token


def create_app():
    return {"routes": ["/health", "/items"]}
'''

_README = "# hello\n\nA tiny fixture repository served by the in-process GitHub MCP mock.\n"

# Canned file bytes keyed by repo-relative POSIX path. Files present in the tree
# but absent here fall back to a generic stub (see ``_file_bytes``).
_CONTENTS: dict[str, str] = {
    "README.md": _README,
    "app/__init__.py": "",
    "app/security.py": _SECURITY_PY,
    "app/main.py": _MAIN_PY,
}

# Recursive tree as the ``get_repository_tree`` tool would return it. The
# ``node_modules`` blob is deliberately present so the adapter's ignore rules are
# exercised (the tree tests assert it is hidden while ``app`` is shown).
_TREE: list[dict[str, Any]] = [
    {"path": "README.md", "type": "blob", "sha": "a0", "size": len(_README.encode())},
    {"path": "app", "type": "tree", "sha": "d0"},
    {"path": "app/__init__.py", "type": "blob", "sha": "a1", "size": 0},
    {"path": "app/security.py", "type": "blob", "sha": "a2", "size": len(_SECURITY_PY.encode())},
    {"path": "app/main.py", "type": "blob", "sha": "a3", "size": len(_MAIN_PY.encode())},
    {"path": "node_modules", "type": "tree", "sha": "d1"},
    {"path": "node_modules/leftpad/index.js", "type": "blob", "sha": "a4", "size": 42},
]


def _text_result(tool: str, payload: Any) -> MCPToolResult:
    """A data-tool result: one JSON ``TextContent`` block, as ``.json()`` expects."""

    block = TextContent(type="text", text=json.dumps(payload))
    return MCPToolResult(tool=tool, content=(block,), structured=None)


def _file_bytes(path: str) -> str:
    if path in _CONTENTS:
        return _CONTENTS[path]
    # Any other tree file: valid, non-JSON text so the adapter returns it verbatim.
    return f"# {path}\n# canned content from the in-process GitHub MCP mock\n"


class FakeGitHubMCPClient:
    """Blocking, in-process stand-in for :class:`GitHubMCPClient`.

    Stateless with respect to owner/repo — those arrive as tool *arguments*, so a
    single instance serves every registered GitHub repo, exactly like the real
    shared session. ``repo_status=404`` simulates an unknown/empty repository.
    """

    def __init__(self, *, repo_status: int = 200) -> None:
        self._repo_status = repo_status
        self._connected = False
        self._closed = False

    # -- lifecycle (used by the registry) --------------------------------- #
    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._closed = True

    def list_tools(self) -> list[str]:
        return list(_READ_TOOLS)

    # -- tool surface (used by GitHubMCPRepository) ----------------------- #
    def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> MCPToolResult:
        args = arguments or {}
        if name == "list_commits":
            return self._list_commits()
        if name == "get_repository_tree":
            return self._repository_tree()
        if name == "get_file_contents":
            return self._file_contents(args)
        if name == "search_code":
            return self._search_code(args)
        # Mirror the real client's typed failure for an unsupported tool rather
        # than returning empty data that would mask a wiring mistake.
        from code_intelligence.errors import GitHubMCPToolError

        raise GitHubMCPToolError(f"The GitHub MCP tool {name!r} is not available in the mock.")

    # -- canned tool payloads --------------------------------------------- #
    def _list_commits(self) -> MCPToolResult:
        if self._repo_status == 404:
            # No commits -> the adapter raises GitHubRepoNotFoundError, the real
            # "repository not found" path, with no network involved.
            return _text_result("list_commits", [])
        commit = {
            "sha": _HEAD_SHA,
            "commit": {"committer": {"date": _HEAD_DATE}, "author": {"date": _HEAD_DATE}},
        }
        return _text_result("list_commits", [commit])

    def _repository_tree(self) -> MCPToolResult:
        return _text_result(
            "get_repository_tree",
            {"sha": _HEAD_SHA, "truncated": False, "tree": _TREE},
        )

    def _file_contents(self, args: dict[str, Any]) -> MCPToolResult:
        path = str(args.get("path") or "")
        block = TextContent(type="text", text=_file_bytes(path))
        return MCPToolResult(tool="get_file_contents", content=(block,), structured=None)

    def _search_code(self, args: dict[str, Any]) -> MCPToolResult:
        payload = {
            "total_count": 1,
            "incomplete_results": False,
            "items": [
                {
                    "path": "app/security.py",
                    "name": "security.py",
                    "text_matches": [
                        {"fragment": "def verify_token(token: str | None):"}
                    ],
                }
            ],
        }
        return _text_result("search_code", payload)

    def __repr__(self) -> str:
        return f"<FakeGitHubMCPClient repo_status={self._repo_status} connected={self._connected}>"


def mock_client(*, repo_status: int = 200) -> FakeGitHubMCPClient:
    """Return an in-process fake GitHub MCP client.

    ``repo_status=404`` simulates a repository with no accessible commits so the
    adapter takes its real not-found path; the default serves the canned repo.
    """

    return FakeGitHubMCPClient(repo_status=repo_status)
