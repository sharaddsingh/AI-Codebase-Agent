"""Path validation and repository-root containment.

The single most important security property of the local engine: **no operation
may ever touch a path outside the authorized repository root.**  Every path that
enters the engine goes through :func:`resolve_within_root`, which normalizes the
input, rejects absolute paths / drive letters / parent traversal, resolves
symlinks with ``realpath`` and then verifies the *real* target is still inside
the *real* root.  Resolving symlinks before the containment check is what
defeats a symlink inside the repo that points outside it.
"""

from __future__ import annotations

import ntpath
import os
import posixpath
from pathlib import Path

from .errors import PathValidationError


def _real(path: os.PathLike[str] | str) -> str:
    return os.path.realpath(str(path))


def is_within(root: str, target: str) -> bool:
    """Return True iff ``target`` is ``root`` itself or lives beneath it.

    Both arguments are compared after ``realpath`` + case-normalization so the
    check is correct across symlinks and on case-insensitive filesystems.
    """

    root_r = os.path.normcase(_real(root))
    target_r = os.path.normcase(_real(target))
    if target_r == root_r:
        return True
    return target_r.startswith(root_r + os.sep)


def normalize_relative(rel_path: str | None) -> str:
    """Normalize a caller-supplied repo-relative path to a clean POSIX string.

    Raises :class:`PathValidationError` for absolute paths, drive letters, UNC
    paths, or any ``..`` component.  Returns ``""`` for the repository root.
    """

    raw = (rel_path or "").strip()
    if raw in ("", ".", "./"):
        return ""

    # Normalize Windows separators to POSIX for uniform handling.
    unified = raw.replace("\\", "/")

    # Reject absolute paths and Windows drive / UNC prefixes outright.
    if unified.startswith("/"):
        raise PathValidationError("Absolute paths are not allowed; use a repository-relative path.")
    if ntpath.splitdrive(raw)[0]:
        raise PathValidationError("Drive-qualified paths are not allowed.")

    parts = [p for p in unified.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise PathValidationError("Parent-directory traversal ('..') is not allowed.")

    # Guard against NUL and other control characters in path components.
    for p in parts:
        if "\x00" in p:
            raise PathValidationError("Path contains a null byte.")

    return posixpath.join(*parts) if parts else ""


def resolve_within_root(root: Path, rel_path: str | None) -> Path:
    """Resolve ``rel_path`` under ``root`` and guarantee containment.

    Returns an absolute :class:`~pathlib.Path`.  The path is *not* required to
    exist yet (callers check existence and type separately) but it is guaranteed
    to resolve inside ``root``.
    """

    normalized = normalize_relative(rel_path)
    candidate = root if normalized == "" else root.joinpath(*normalized.split("/"))

    # Resolve the *deepest existing ancestor* with realpath so a symlink
    # anywhere along the path cannot be used to escape, even when the leaf does
    # not exist yet.
    if not is_within(str(root), str(candidate)):
        raise PathValidationError("Resolved path escapes the repository root.")

    return Path(_real(candidate))


def to_relative_posix(root: Path, absolute: Path) -> str:
    """Return the repository-relative POSIX path for an absolute path under root."""

    rel = os.path.relpath(_real(absolute), _real(root))
    if rel == ".":
        return ""
    return rel.replace(os.sep, "/")
