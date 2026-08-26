"""LocalRepositoryAdapter: the implemented capabilities work; the deferred ones
raise NotSupportedError (documented surface, not yet built)."""

from __future__ import annotations

import pytest

from code_intelligence.errors import NotSupportedError
from code_intelligence.models import RepositoryKind


def test_kind_is_local(repo) -> None:
    assert repo.kind == RepositoryKind.local


def test_snapshot_has_stable_id(repo) -> None:
    snap = repo.get_snapshot()
    assert snap.id.startswith(("git:", "wt:"))
    # Snapshot is captured once and returned consistently.
    assert repo.get_snapshot().id == snap.id


def test_implemented_capabilities(repo) -> None:
    assert repo.list_files("").total >= 1
    assert repo.get_file_metadata("app/security.py").line_count == 49
    assert repo.read_file("app/security.py", start_line=1, end_line=3).end_line == 3
    assert repo.search_code("verify_token").total_matches >= 1


@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.find_symbol("verify_token"),
        lambda r: r.find_references("app/security.py", 25, 0),
        lambda r: r.get_dependencies("app/security.py"),
    ],
)
def test_deferred_capabilities_raise(repo, call) -> None:
    with pytest.raises(NotSupportedError):
        call(repo)
