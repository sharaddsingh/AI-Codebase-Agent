"""File metadata: language, line count, binary detection, hashing."""

from __future__ import annotations

import pytest

from code_intelligence.engine import get_metadata
from code_intelligence.errors import NotAFileError, PathNotFoundError


def test_metadata_python_file(repo) -> None:
    m = get_metadata(repo.root, repo.id, "app/security.py")
    assert m.language == "python"
    assert m.is_binary is False
    assert m.line_count == 49
    assert m.size_bytes > 0
    assert len(m.sha256) == 64  # hex sha256


def test_metadata_binary_file(repo) -> None:
    m = get_metadata(repo.root, repo.id, "assets/logo.bin")
    assert m.is_binary is True
    assert m.line_count is None  # not counted for binary
    assert len(m.sha256) == 64


def test_metadata_hash_is_stable(repo) -> None:
    a = get_metadata(repo.root, repo.id, "app/security.py")
    b = get_metadata(repo.root, repo.id, "app/security.py")
    assert a.sha256 == b.sha256


def test_metadata_missing_errors(repo) -> None:
    with pytest.raises(PathNotFoundError):
        get_metadata(repo.root, repo.id, "app/nope.py")


def test_metadata_directory_errors(repo) -> None:
    with pytest.raises(NotAFileError):
        get_metadata(repo.root, repo.id, "app")
