"""API integration tests via FastAPI's TestClient.

The agent endpoint is driven by a scripted MockAdapter injected through
``deps.set_model_adapter``, so the whole stack (registration → tree/file/search →
SSE agent run) is exercised without an API key or network call.
"""

from __future__ import annotations

import json
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


@pytest.fixture
def repo_id(client: TestClient, sample_repo_path: Path) -> str:
    r = client.post("/api/repositories", json={"path": str(sample_repo_path), "name": "sample"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["model_configured"], bool)


def test_register_and_tree(client: TestClient, repo_id: str) -> None:
    r = client.get(f"/api/repositories/{repo_id}/tree", params={"path": ""})
    assert r.status_code == 200
    names = {e["name"] for e in r.json()["entries"]}
    assert "app" in names
    assert "node_modules" not in names


def test_file_endpoint(client: TestClient, repo_id: str) -> None:
    r = client.get(
        f"/api/repositories/{repo_id}/file",
        params={"path": "app/security.py", "start_line": 1, "end_line": 5},
    )
    assert r.status_code == 200
    assert r.json()["end_line"] == 5


def test_search_endpoint(client: TestClient, repo_id: str) -> None:
    r = client.get(f"/api/repositories/{repo_id}/search", params={"query": "verify_token"})
    assert r.status_code == 200
    assert r.json()["total_matches"] >= 1


def test_metadata_endpoint(client: TestClient, repo_id: str) -> None:
    r = client.get(f"/api/repositories/{repo_id}/metadata", params={"path": "app/security.py"})
    assert r.status_code == 200
    assert r.json()["language"] == "python"


def test_traversal_returns_400(client: TestClient, repo_id: str) -> None:
    r = client.get(
        f"/api/repositories/{repo_id}/file", params={"path": "../../../etc/passwd"}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "path_validation_error"


def test_unknown_repo_returns_404(client: TestClient) -> None:
    r = client.get("/api/repositories/repo_missing/tree", params={"path": ""})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "repository_not_found"


def _sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into a list of (event, data) pairs."""
    events: list[tuple[str, dict]] = []
    event_name: str | None = None
    for line in text.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:") and event_name is not None:
            raw = line[len("data:"):].strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            events.append((event_name, data))
            event_name = None
    return events


def test_agent_chat_streams_answer(client: TestClient, repo_id: str) -> None:
    r = client.post(
        "/api/agent/chat", json={"repo_id": repo_id, "question": "Why does it return 401?"}
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    events = _sse_events(r.text)
    types = [name for name, _ in events]
    assert "classified" in types
    assert "answer" in types
    assert "done" in types

    answer_data = next(data for name, data in events if name == "answer")
    result = answer_data["data"]  # AgentResult nested in the AgentEvent
    assert any(c["path"] == "app/security.py" for c in result["citations"])
    assert result["stop_reason"] == "answered"


def test_agent_chat_unknown_repo_streams_error(client: TestClient) -> None:
    r = client.post("/api/agent/chat", json={"repo_id": "repo_missing", "question": "hi"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    types = [name for name, _ in events]
    assert "error" in types
    assert "done" in types


# ---- GitHub repositories through the real API route (mocked network) --------
# The registry's GitHubClient is backed by httpx.MockTransport, so POSTing a
# GitHub URL exercises the whole stack — source detection, adapter, tree/file/
# search, and an agent run — without ever reaching github.com.

GH_URL = "https://github.com/octocat/hello"


@pytest.fixture
def gh_client() -> Iterator[TestClient]:
    deps.reset_state()
    deps.set_registry(RepositoryRegistry(github_client=mock_client()))
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
    r = gh_client.post("/api/repositories", json={"path": GH_URL})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_register_github_url(gh_client: TestClient) -> None:
    r = gh_client.post("/api/repositories", json={"path": GH_URL})
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
    assert body["engine"] == "github-api"


def test_github_traversal_returns_400(gh_client: TestClient, gh_repo_id: str) -> None:
    # GitHub paths use the same pure-string validation as local ones.
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
        "/api/repositories",
        json={"path": "https://github.com/octocat/hello/blob/main/app/security.py"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_github_url"


def test_missing_github_repo_returns_404() -> None:
    deps.reset_state()
    deps.set_registry(RepositoryRegistry(github_client=mock_client(repo_status=404)))
    try:
        with TestClient(app) as c:
            r = c.post("/api/repositories", json={"path": GH_URL})
            assert r.status_code == 404
            assert r.json()["error"]["code"] == "github_repo_not_found"
    finally:
        deps.reset_state()
