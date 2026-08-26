"""Lexical search: the pure-Python fallback always runs here; ripgrep is
exercised only when it is installed (it is not required for the MVP)."""

from __future__ import annotations

import pytest

from code_intelligence.errors import SearchError
from code_intelligence.limits import DEFAULT_LIMITS
from retrieval.lexical import (
    _search_python,
    _search_ripgrep,
    ripgrep_available,
    search,
)


def _py(repo, query, **kw):
    return _search_python(
        repo.root,
        repo.ignore,
        query,
        regex=kw.get("regex", False),
        case_sensitive=kw.get("case_sensitive", False),
        path_glob=kw.get("path_glob"),
        max_results=kw.get("max_results", 100),
        limits=DEFAULT_LIMITS,
        repo_id=repo.id,
    )


def test_python_fallback_finds_matches(repo) -> None:
    res = _py(repo, "verify_token")
    assert res.engine == "python-fallback"
    assert res.total_matches >= 1
    assert "app/security.py" in {m.path for m in res.matches}


def test_search_excludes_ignored_dirs(repo) -> None:
    # "leftpad" content lives only under node_modules/, which is ignored.
    res = _py(repo, "leftpad")
    assert all("node_modules" not in m.path for m in res.matches)


def test_search_regex(repo) -> None:
    res = _py(repo, r"def\s+verify_\w+", regex=True)
    assert res.total_matches >= 1
    assert all(m.line_number >= 1 for m in res.matches)


def test_search_path_glob(repo) -> None:
    res = _py(repo, "import", path_glob="*.md")
    assert all(m.path.endswith(".md") for m in res.matches)


def test_empty_query_raises(repo) -> None:
    with pytest.raises(SearchError):
        search(repo.root, repo.ignore, "   ", repo_id=repo.id)


def test_public_search_finds(repo) -> None:
    res = repo.search_code("verify_token")
    assert res.total_matches >= 1
    assert res.engine in ("ripgrep", "python-fallback")


@pytest.mark.skipif(not ripgrep_available(), reason="ripgrep not installed")
def test_ripgrep_engine(repo) -> None:
    res = _search_ripgrep(
        repo.root,
        repo.ignore,
        "verify_token",
        regex=False,
        case_sensitive=False,
        path_glob=None,
        max_results=100,
        limits=DEFAULT_LIMITS,
        repo_id=repo.id,
    )
    assert res.engine == "ripgrep"
    assert res.total_matches >= 1
    assert "app/security.py" in {m.path for m in res.matches}
