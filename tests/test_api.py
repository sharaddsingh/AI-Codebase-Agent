"""API integration tests via FastAPI's TestClient.

The agent endpoint is driven by a scripted MockAdapter injected through
``deps.set_model_adapter``, so the whole stack (registration → tree/file/search
→ SSE agent run) is exercised without an API key or network call.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from github_mock import mock_client

from agent.model_adapter import MockAdapter, final_answer, tool_call
from backend import deps
from backend.main import app
from code_intelligence.registry import RepositoryRegistry


@pytest.fixture
def client() -> Iterator[TestClient]:
    deps.reset_state()
    deps.set_model_adapter(
        MockAdapter(
            [
                tool_call("search_code", {"query": "verify_token"}),
                tool_call(
                    "read_file",
                    {"path": "app/security.py", "start_line": 1, "end_line": 49},
                ),
                final_answer(
                    "The 401 comes from verify_token (app/security.py:25-49).\n\n"
                    "Sources: app/security.py:25-49"
                ),
            ]
        )
    )
    with TestClient(app) as c:
        yield c
    deps.reset_state()


def _upload_repo(client: TestClient, sample_repo_path: Path, name: str = "sample") -> str:
    """Upload the bundled fixture as a multipart folder and return the new id."""

    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for p in sample_repo_path.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(sample_repo_path).as_posix()
        files.append(
            ("files", (rel, p.read_bytes(), _content_type_for(p)))
        )
    r = client.post("/api/repositories/upload", files=files, data={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _content_type_for(p: Path) -> str:
    if p.suffix in {".md", ".txt"}:
        return "text/plain"
    if p.suffix == ".py":
        return "text/x-python"
    if p.suffix == ".js":
        return "application/javascript"
    if p.suffix == ".json":
        return "application/json"
    if p.suffix == ".bin":
        return "application/octet-stream"
    return "application/octet-stream"


@pytest.fixture
def repo_id(client: TestClient, sample_repo_path: Path, tmp_path: Path) -> str:
    # Copy the fixture into a stable upload root so each test owns a clean tree.
    upload_root = deps.get_upload_root()
    upload_root.mkdir(parents=True, exist_ok=True)
    fixture_copy = upload_root / "fixture-sample"
    if fixture_copy.exists():
        shutil.rmtree(fixture_copy)
    shutil.copytree(sample_repo_path, fixture_copy)
    return _upload_repo(client, fixture_copy, name="sample")


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["model_configured"], bool)
    assert "unrestricted_roots" not in body  # legacy field is gone


def test_upload_registers_repo(client: TestClient, repo_id: str) -> None:
    r = client.get("/api/repositories")
    assert r.status_code == 200
    ids = {entry["id"] for entry in r.json()}
    assert repo_id in ids


def test_upload_shows_the_picked_folder_name(client: TestClient, repo_id: str) -> None:
    # The card in the UI is labelled with `name`. Before the form field was
    # plumbed through, every upload came back named after its content-hash
    # directory ("up_ab12...") and looked like it had not been added at all.
    info = next(r for r in client.get("/api/repositories").json() if r["id"] == repo_id)
    assert info["name"] == "sample"


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        ("my-project", "my-project"),
        # A browser may hand us a whole relative path; only the leaf is a name.
        ("C:\\Users\\me\\my-project", "my-project"),
        ("nested/deep/my-project", "my-project"),
        ("  spaced  ", "spaced"),
        ("bad\u0000name", "badname"),
        ("x" * 200, "x" * 80),
    ],
)
def test_upload_name_is_sanitized(client: TestClient, sent: str, expected: str) -> None:
    r = client.post(
        "/api/repositories/upload",
        files=[("files", ("app/main.py", b"print('hi')\n", "text/x-python"))],
        data={"name": sent},
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == expected


@pytest.mark.parametrize("sent", ["", ".", "..", "   ", "/", "\u0000"])
def test_upload_falls_back_when_the_name_is_unusable(client: TestClient, sent: str) -> None:
    # Nothing usable survives sanitizing, so the server names the repo after the
    # directory it owns rather than trusting or rejecting the input.
    r = client.post(
        "/api/repositories/upload",
        files=[("files", ("app/main.py", b"print('hi')\n", "text/x-python"))],
        data={"name": sent},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == Path(body["root"]).name
    assert body["name"].startswith("up_")


def test_upload_without_a_name_uses_the_upload_directory(client: TestClient) -> None:
    r = client.post(
        "/api/repositories/upload",
        files=[("files", ("app/main.py", b"print('hi')\n", "text/x-python"))],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == Path(body["root"]).name


def test_uploaded_tree_hides_ignored(client: TestClient, repo_id: str) -> None:
    r = client.get(f"/api/repositories/{repo_id}/tree", params={"path": ""})
    assert r.status_code == 200
    names = {e["name"] for e in r.json()["entries"]}
    assert "app" in names
    assert "node_modules" not in names


def test_uploaded_file_endpoint(client: TestClient, repo_id: str) -> None:
    r = client.get(
        f"/api/repositories/{repo_id}/file",
        params={"path": "app/security.py", "start_line": 1, "end_line": 5},
    )
    assert r.status_code == 200
    assert r.json()["end_line"] == 5


def test_uploaded_search_endpoint(client: TestClient, repo_id: str) -> None:
    r = client.get(f"/api/repositories/{repo_id}/search", params={"query": "verify_token"})
    assert r.status_code == 200
    assert r.json()["total_matches"] >= 1


def test_uploaded_metadata_endpoint(client: TestClient, repo_id: str) -> None:
    r = client.get(f"/api/repositories/{repo_id}/metadata", params={"path": "app/security.py"})
    assert r.status_code == 200
    assert r.json()["language"] == "python"


def test_uploaded_traversal_returns_400(client: TestClient, repo_id: str) -> None:
    r = client.get(
        f"/api/repositories/{repo_id}/file", params={"path": "../../../etc/passwd"}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "path_validation_error"


def test_unknown_repo_returns_404(client: TestClient) -> None:
    r = client.get("/api/repositories/repo_missing/tree", params={"path": ""})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "repository_not_found"


def test_remove_uploaded_repo_wipes_disk(client: TestClient, repo_id: str) -> None:
    # Find the on-disk root before removal.
    listing = client.get("/api/repositories").json()
    info = next(r for r in listing if r["id"] == repo_id)
    root = Path(info["root"])
    assert root.is_dir()

    assert client.delete(f"/api/repositories/{repo_id}").status_code == 204
    # Registry-side: gone.
    assert client.get(f"/api/repositories/{repo_id}").status_code == 404
    assert all(r["id"] != repo_id for r in client.get("/api/repositories").json())
    # Disk-side: the per-repo upload directory is removed.
    assert not root.exists()


def test_remove_unknown_repo_returns_404(client: TestClient) -> None:
    r = client.delete("/api/repositories/repo_missing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "repository_not_found"


def _sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into a list of (event, data) pairs."""
    events: list[tuple[str, dict]] = []
    event: str | None = None
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
        elif line == "" and event is not None:
            data = json.loads("\n".join(data_lines)) if data_lines else {}
            events.append((event, data))
            event = None
            data_lines = []
    if event is not None:
        data = json.loads("\n".join(data_lines)) if data_lines else {}
        events.append((event, data))
    return events


def test_agent_chat_unknown_repo_streams_error(client: TestClient) -> None:
    r = client.post("/api/agent/chat", json={"repo_id": "repo_missing", "question": "hi"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    types = [name for name, _ in events]
    assert "error" in types
    assert "done" in types


# ---- GitHub repositories through the real API route (mocked network) -------
# The registry's GitHub MCP client is replaced by an in-process fake (github_mock),
# so POSTing a GitHub URL exercises the whole stack — source detection, adapter,
# tree/file/search, and an agent run — without ever reaching github.com.

GH_URL = "https://github.com/octocat/hello"


@pytest.fixture
def gh_client() -> Iterator[TestClient]:
    deps.reset_state()
    deps.set_registry(RepositoryRegistry(github_mcp_client=mock_client()))
    deps.set_model_adapter(
        MockAdapter(
            [
                tool_call("search_code", {"query": "verify_token"}),
                tool_call(
                    "read_file",
                    {"path": "app/security.py", "start_line": 1, "end_line": 4},
                ),
                final_answer(
                    "verify_token raises the 401 (app/security.py:1-4).\n\n"
                    "Sources: app/security.py:1-4"
                ),
            ]
        )
    )
    with TestClient(app) as c:
        yield c
    deps.reset_state()


@pytest.fixture
def gh_repo_id(gh_client: TestClient) -> str:
    r = gh_client.post("/api/repositories/github", json={"url": GH_URL})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_register_github_url(gh_client: TestClient) -> None:
    r = gh_client.post("/api/repositories/github", json={"url": GH_URL})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "github"
    assert body["root"] == GH_URL
    assert body["snapshot"]["id"].startswith("gh:")


def test_github_tree_hides_ignored(gh_client: TestClient, gh_repo_id: str) -> None:
    r = gh_client.get(f"/api/repositories/{gh_repo_id}/tree", params={"path": ""})
    assert r.status_code == 200
    names = {e["name"] for e in r.json()["entries"]}
    assert "app" in names
    assert "node_modules" not in names


def test_github_file_read(gh_client: TestClient, gh_repo_id: str) -> None:
    r = gh_client.get(
        f"/api/repositories/{gh_repo_id}/file",
        params={"path": "app/security.py", "start_line": 1, "end_line": 4},
    )
    assert r.status_code == 200
    assert "verify_token" in r.json()["content"]


def test_github_search(gh_client: TestClient, gh_repo_id: str) -> None:
    r = gh_client.get(
        f"/api/repositories/{gh_repo_id}/search", params={"query": "verify_token"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_matches"] >= 1
    assert body["engine"] == "github-mcp"


def test_github_traversal_returns_400(gh_client: TestClient, gh_repo_id: str) -> None:
    r = gh_client.get(
        f"/api/repositories/{gh_repo_id}/file", params={"path": "../../../etc/passwd"}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "path_validation_error"


def test_github_agent_streams_answer_with_citations(
    gh_client: TestClient, gh_repo_id: str
) -> None:
    r = gh_client.post(
        "/api/agent/chat",
        json={"repo_id": gh_repo_id, "question": "Where does the 401 come from?"},
    )
    assert r.status_code == 200
    events = _sse_events(r.text)
    types = [name for name, _ in events]
    assert "answer" in types
    assert "done" in types
    answer_data = next(data for name, data in events if name == "answer")
    result = answer_data["data"]
    assert any(c["path"] == "app/security.py" for c in result["citations"])
    assert result["stop_reason"] == "answered"


def test_invalid_github_url_returns_400(gh_client: TestClient) -> None:
    # A deep link inside a repo is detected as GitHub but is not a repo root.
    r = gh_client.post(
        "/api/repositories/github",
        json={"url": "https://github.com/octocat/hello/blob/main/app/security.py"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_github_url"


def test_missing_github_repo_returns_404() -> None:
    deps.reset_state()
    deps.set_registry(RepositoryRegistry(github_mcp_client=mock_client(repo_status=404)))
    try:
        with TestClient(app) as c:
            r = c.post("/api/repositories/github", json={"url": GH_URL})
            assert r.status_code == 404
            assert r.json()["error"]["code"] == "github_repository_not_found"
    finally:
        deps.reset_state()


def test_github_metadata_endpoint(gh_client: TestClient, gh_repo_id: str) -> None:
    r = gh_client.get(
        f"/api/repositories/{gh_repo_id}/metadata", params={"path": "app/security.py"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "python"
    assert body["is_binary"] is False
    assert body["modified_at"]


@pytest.mark.parametrize("commit_date", [None, "not-a-real-date"])
def test_github_metadata_survives_an_unparsable_commit_date(commit_date: str | None) -> None:
    # `modified_at` is a required datetime on FileMetadata, so an unparsable head
    # commit date used to fail model validation and 500 every metadata request.
    # The adapter now falls back to the load time.
    deps.reset_state()
    deps.set_registry(RepositoryRegistry(github_mcp_client=mock_client(commit_date=commit_date)))
    try:
        with TestClient(app) as c:
            reg = c.post("/api/repositories/github", json={"url": GH_URL})
            assert reg.status_code == 201, reg.text
            repo_id = reg.json()["id"]

            r = c.get(
                f"/api/repositories/{repo_id}/metadata", params={"path": "app/security.py"}
            )
            assert r.status_code == 200, r.text
            assert r.json()["modified_at"]
    finally:
        deps.reset_state()
