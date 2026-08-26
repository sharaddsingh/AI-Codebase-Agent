"""Directory listing: ignores, ordering, pagination, errors."""

from __future__ import annotations

import pytest

from code_intelligence.engine import build_directory_listing
from code_intelligence.errors import NotADirError, PathNotFoundError, PathValidationError


def test_root_listing_excludes_ignored(repo) -> None:
    listing = build_directory_listing(repo.root, repo.id, "", ignore=repo.ignore)
    names = {e.name for e in listing.entries}
    assert "app" in names
    assert "README.md" in names
    assert "node_modules" not in names  # ignored dir


def test_dirs_sorted_first(repo) -> None:
    listing = build_directory_listing(repo.root, repo.id, "", ignore=repo.ignore)
    types = [e.type.value for e in listing.entries]
    first_file = next((i for i, t in enumerate(types) if t == "file"), len(types))
    assert all(t == "dir" for t in types[:first_file])


def test_pagination(repo) -> None:
    full = build_directory_listing(repo.root, repo.id, "", ignore=repo.ignore)
    page1 = build_directory_listing(
        repo.root, repo.id, "", page=1, page_size=2, ignore=repo.ignore
    )
    assert len(page1.entries) == 2
    assert page1.total == full.total
    assert page1.truncated is (full.total > 2)


def test_listing_subdir(repo) -> None:
    listing = build_directory_listing(repo.root, repo.id, "app", ignore=repo.ignore)
    names = {e.name for e in listing.entries}
    assert {"main.py", "security.py", "auth.py"} <= names


def test_list_file_as_dir_errors(repo) -> None:
    with pytest.raises(NotADirError):
        build_directory_listing(repo.root, repo.id, "README.md", ignore=repo.ignore)


def test_list_missing_errors(repo) -> None:
    with pytest.raises(PathNotFoundError):
        build_directory_listing(repo.root, repo.id, "does/not/exist", ignore=repo.ignore)


def test_list_traversal_blocked(repo) -> None:
    with pytest.raises(PathValidationError):
        build_directory_listing(repo.root, repo.id, "../..", ignore=repo.ignore)
