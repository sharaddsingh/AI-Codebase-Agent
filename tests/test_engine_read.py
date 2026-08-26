"""Reading files: windows, byte budgets, binary refusal, containment."""

from __future__ import annotations

import pytest

from code_intelligence.engine import read_text_file
from code_intelligence.errors import (
    BinaryFileError,
    NotAFileError,
    PathNotFoundError,
    PathValidationError,
)


def test_read_full_file(repo) -> None:
    fc = read_text_file(repo.root, repo.id, "app/security.py")
    assert fc.total_lines == 49
    assert fc.start_line == 1
    assert fc.end_line == 49
    assert "verify_token" in fc.content
    assert fc.encoding == "utf-8"


def test_read_line_window(repo) -> None:
    fc = read_text_file(repo.root, repo.id, "app/security.py", start_line=1, end_line=5)
    assert fc.start_line == 1
    assert fc.end_line == 5
    assert len(fc.content.split("\n")) == 5


def test_read_byte_budget_truncates(repo) -> None:
    # A tiny byte budget forces truncation after the first line.
    fc = read_text_file(repo.root, repo.id, "app/security.py", max_bytes=10)
    assert fc.truncated is True
    assert fc.end_line < fc.total_lines


def test_read_binary_refused(repo) -> None:
    with pytest.raises(BinaryFileError):
        read_text_file(repo.root, repo.id, "assets/logo.bin")


def test_read_directory_errors(repo) -> None:
    with pytest.raises(NotAFileError):
        read_text_file(repo.root, repo.id, "app")


def test_read_missing_errors(repo) -> None:
    with pytest.raises(PathNotFoundError):
        read_text_file(repo.root, repo.id, "app/nope.py")


def test_read_traversal_blocked(repo) -> None:
    with pytest.raises(PathValidationError):
        read_text_file(repo.root, repo.id, "../../../etc/passwd")
