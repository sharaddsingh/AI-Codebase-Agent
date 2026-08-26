"""MCP server contract tests.

The server module is loaded by path (it is intentionally not a package) and
driven through the official MCP SDK's in-memory ``Client`` — the same protocol a
real MCP client would speak. We assert the tool surface and that the security
properties (containment, binary refusal, allow-list) hold across the boundary.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from mcp import Client

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("mcp_server_under_test", SERVER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def server_mod():
    return _load_server()


async def test_tools_are_listed(server_mod) -> None:
    async with Client(server_mod.server) as client:
        res = await client.list_tools()
        names = {t.name for t in res.tools}
        assert {
            "list_files",
            "read_file",
            "search_code",
            "get_file_metadata",
            "get_repository_snapshot",
        } <= names


async def test_search_and_read(server_mod, sample_repo_path: Path) -> None:
    root = str(sample_repo_path)
    async with Client(server_mod.server) as client:
        r = await client.call_tool("search_code", {"repo_root": root, "query": "verify_token"})
        assert r.is_error is False
        data = json.loads(r.content[0].text)
        assert data["total_matches"] >= 1

        r = await client.call_tool(
            "read_file", {"repo_root": root, "path": "app/security.py", "start_line": 1, "end_line": 5}
        )
        assert r.is_error is False
        content = json.loads(r.content[0].text)
        assert content["end_line"] == 5


async def test_list_files_excludes_ignored(server_mod, sample_repo_path: Path) -> None:
    async with Client(server_mod.server) as client:
        r = await client.call_tool("list_files", {"repo_root": str(sample_repo_path), "path": ""})
        assert r.is_error is False
        listing = json.loads(r.content[0].text)
        names = {e["name"] for e in listing["entries"]}
        assert "node_modules" not in names


async def test_snapshot_tool(server_mod, sample_repo_path: Path) -> None:
    async with Client(server_mod.server) as client:
        r = await client.call_tool("get_repository_snapshot", {"repo_root": str(sample_repo_path)})
        assert r.is_error is False
        payload = json.loads(r.content[0].text)
        assert payload["snapshot"]["id"].startswith(("git:", "wt:"))


async def test_traversal_blocked(server_mod, sample_repo_path: Path) -> None:
    async with Client(server_mod.server) as client:
        r = await client.call_tool(
            "read_file", {"repo_root": str(sample_repo_path), "path": "../../../etc/passwd"}
        )
        assert r.is_error is True


async def test_binary_refused(server_mod, sample_repo_path: Path) -> None:
    async with Client(server_mod.server) as client:
        r = await client.call_tool(
            "read_file", {"repo_root": str(sample_repo_path), "path": "assets/logo.bin"}
        )
        assert r.is_error is True


async def test_allowed_roots_enforced(server_mod, sample_repo_path: Path, monkeypatch) -> None:
    # Restrict the server to a subdirectory; the parent repo root is then off-limits.
    monkeypatch.setenv("MCP_ALLOWED_ROOTS", str(sample_repo_path / "app"))
    async with Client(server_mod.server) as client:
        r = await client.call_tool("list_files", {"repo_root": str(sample_repo_path), "path": ""})
        assert r.is_error is True
