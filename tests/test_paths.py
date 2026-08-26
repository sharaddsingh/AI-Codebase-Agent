"""Containment and path-validation — the core security property."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_intelligence.errors import PathValidationError
from code_intelligence.paths import (
    is_within,
    normalize_relative,
    resolve_within_root,
    to_relative_posix,
)


@pytest.mark.parametrize("raw", ["", ".", "./"])
def test_normalize_root_variants(raw: str) -> None:
    assert normalize_relative(raw) == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a/b/c.py", "a/b/c.py"),
        ("a\\b\\c.py", "a/b/c.py"),   # windows separators normalized
        ("./a/./b", "a/b"),
        ("a//b", "a/b"),
    ],
)
def test_normalize_relative_ok(raw: str, expected: str) -> None:
    assert normalize_relative(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "/etc/passwd",          # absolute
        "../secrets",           # parent traversal
        "a/../../b",            # traversal in the middle
        "C:\\Windows",          # drive-qualified
        "\\\\server\\share",    # UNC
        "a/\x00/b",             # null byte
    ],
)
def test_normalize_relative_rejects(raw: str) -> None:
    with pytest.raises(PathValidationError):
        normalize_relative(raw)


def test_is_within(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    assert is_within(str(root), str(root))                 # root itself
    assert is_within(str(root), str(root / "sub"))         # child
    assert not is_within(str(root), str(tmp_path / "other"))  # sibling
    # Prefix that is not a path boundary must not count as "within".
    (tmp_path / "repo_evil").mkdir()
    assert not is_within(str(root), str(tmp_path / "repo_evil"))


def test_resolve_within_root_ok(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    resolved = resolve_within_root(root, "pkg/mod.py")
    assert is_within(str(root), str(resolved))


def test_resolve_within_root_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(PathValidationError):
        resolve_within_root(root, "../escape")


def test_symlink_escape_blocked(tmp_path: Path) -> None:
    """A symlink inside the repo that points outside must not grant access."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("top secret")
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform/user")
    # normalize_relative allows 'link/secret.txt' (no '..'), but realpath of the
    # resolved target lands outside root, so containment must reject it.
    with pytest.raises(PathValidationError):
        resolve_within_root(root, "link/secret.txt")


def test_to_relative_posix(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "a").mkdir(parents=True)
    assert to_relative_posix(root, root / "a" / "b.py") == "a/b.py"
    assert to_relative_posix(root, root) == ""
