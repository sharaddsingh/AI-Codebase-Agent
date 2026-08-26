"""Filesystem operations for a single repository root.

Every function here takes an already-resolved ``root`` and a caller-supplied
repo-relative path, and routes that path through :func:`resolve_within_root`
before touching disk.  All responses are bounded per :class:`EngineLimits`.
These functions are pure with respect to the filesystem (read-only) and know
nothing about HTTP, MCP, or the LLM.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from .content import slice_text_content
from .errors import (
    BinaryFileError,
    NotADirError,
    NotAFileError,
    PathNotFoundError,
)
from .ignore import IgnoreRules
from .languages import guess_language, is_binary_ext, looks_binary
from .limits import DEFAULT_LIMITS, EngineLimits
from .models import (
    DirectoryListing,
    FileContent,
    FileEntry,
    FileMetadata,
    FileType,
)
from .paths import resolve_within_root, to_relative_posix


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def build_directory_listing(
    root: Path,
    repo_id: str,
    rel_path: str | None,
    *,
    page: int = 1,
    page_size: int | None = None,
    ignore: IgnoreRules,
    limits: EngineLimits = DEFAULT_LIMITS,
) -> DirectoryListing:
    abs_dir = resolve_within_root(root, rel_path)
    if not abs_dir.exists():
        raise PathNotFoundError(f"Directory not found: {rel_path or '.'}")
    if not abs_dir.is_dir():
        raise NotADirError(f"Not a directory: {rel_path or '.'}")

    page = max(1, page)
    size = page_size or limits.default_page_size
    size = max(1, min(size, limits.max_page_size))

    entries: list[FileEntry] = []
    with os.scandir(abs_dir) as it:
        for entry in it:
            name = entry.name
            rel = to_relative_posix(root, Path(entry.path))
            is_dir = entry.is_dir(follow_symlinks=False)
            if ignore.is_ignored(rel, is_dir):
                continue
            if entry.is_symlink():
                ftype = FileType.symlink
                fsize: int | None = None
            elif is_dir:
                ftype = FileType.dir
                fsize = None
            elif entry.is_file(follow_symlinks=False):
                ftype = FileType.file
                try:
                    fsize = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    fsize = None
            else:
                ftype = FileType.other
                fsize = None
            entries.append(FileEntry(path=rel, name=name, type=ftype, size=fsize))

    # Directories first, then files, each alphabetical (case-insensitive).
    entries.sort(key=lambda e: (e.type != FileType.dir, e.name.lower()))

    total = len(entries)
    start = (page - 1) * size
    end = start + size
    page_entries = entries[start:end]

    return DirectoryListing(
        repo_id=repo_id,
        path=to_relative_posix(root, abs_dir),
        entries=page_entries,
        total=total,
        page=page,
        page_size=size,
        truncated=end < total,
    )


def _sniff_binary(abs_path: Path, limits: EngineLimits) -> bytes:
    with open(abs_path, "rb") as fh:
        return fh.read(limits.binary_sniff_bytes)


def read_text_file(
    root: Path,
    repo_id: str,
    rel_path: str,
    *,
    start_line: int | None = None,
    end_line: int | None = None,
    max_bytes: int | None = None,
    ignore: IgnoreRules | None = None,  # noqa: ARG001 - kept for signature symmetry
    limits: EngineLimits = DEFAULT_LIMITS,
) -> FileContent:
    abs_path = resolve_within_root(root, rel_path)
    if not abs_path.exists():
        raise PathNotFoundError(f"File not found: {rel_path}")
    if abs_path.is_dir():
        raise NotAFileError(f"Path is a directory, not a file: {rel_path}")
    if not abs_path.is_file():
        raise NotAFileError(f"Not a regular file: {rel_path}")

    if is_binary_ext(abs_path.name):
        raise BinaryFileError(f"Refusing to read binary file: {rel_path}")

    with open(abs_path, "rb") as fh:
        sniff = fh.read(limits.binary_sniff_bytes)
        if looks_binary(sniff):
            raise BinaryFileError(f"Refusing to read binary file: {rel_path}")
        fh.seek(0)
        raw = fh.read(limits.max_readable_file_bytes + 1)

    file_truncated = len(raw) > limits.max_readable_file_bytes
    raw = raw[: limits.max_readable_file_bytes]
    # Slicing/decoding/budgeting is shared with the GitHub adapter via content.py
    # so a read means exactly the same thing regardless of the byte source.
    return slice_text_content(
        repo_id,
        to_relative_posix(root, abs_path),
        raw,
        file_truncated=file_truncated,
        start_line=start_line,
        end_line=end_line,
        max_bytes=max_bytes,
        limits=limits,
    )


def get_metadata(
    root: Path,
    repo_id: str,
    rel_path: str,
    *,
    limits: EngineLimits = DEFAULT_LIMITS,
) -> FileMetadata:
    abs_path = resolve_within_root(root, rel_path)
    if not abs_path.exists():
        raise PathNotFoundError(f"File not found: {rel_path}")
    if not abs_path.is_file():
        raise NotAFileError(f"Not a regular file: {rel_path}")

    st = abs_path.stat()
    is_bin = is_binary_ext(abs_path.name) or looks_binary(_sniff_binary(abs_path, limits))

    line_count: int | None = None
    sha = hashlib.sha256()
    newlines = 0
    last_byte = b""
    with open(abs_path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            sha.update(chunk)
            if not is_bin:
                newlines += chunk.count(b"\n")
                last_byte = chunk[-1:]
    if not is_bin:
        line_count = newlines + (1 if st.st_size > 0 and last_byte != b"\n" else 0)

    return FileMetadata(
        repo_id=repo_id,
        path=to_relative_posix(root, abs_path),
        size_bytes=st.st_size,
        line_count=line_count,
        language=guess_language(abs_path.name),
        is_binary=is_bin,
        modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        sha256=sha.hexdigest(),
    )


def walk_files(
    root: Path,
    ignore: IgnoreRules,
    *,
    limits: EngineLimits = DEFAULT_LIMITS,
    max_files: int | None = None,
) -> Iterator[tuple[str, Path]]:
    """Yield ``(rel_posix, abs_path)`` for non-ignored files, depth-first.

    Symlinked directories are not followed (``os.walk`` default), which prevents
    a symlink cycle or escape during traversal.  Bounded by ``max_files``.
    """

    cap = max_files or limits.walk_file_cap
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = to_relative_posix(root, Path(dirpath))
        # Prune ignored directories in place so os.walk does not descend into them.
        dirnames[:] = [
            d
            for d in dirnames
            if not ignore.is_ignored_dir_name(d)
            and not ignore.is_ignored(posixpath.join(rel_dir, d) if rel_dir else d, True)
        ]
        dirnames.sort(key=str.lower)
        for fn in sorted(filenames, key=str.lower):
            rel = posixpath.join(rel_dir, fn) if rel_dir else fn
            if ignore.is_ignored(rel, False):
                continue
            yield rel, Path(dirpath) / fn
            count += 1
            if count >= cap:
                return


def count_files(
    root: Path,
    ignore: IgnoreRules,
    *,
    cap: int = 5000,
    limits: EngineLimits = DEFAULT_LIMITS,
) -> int:
    """Best-effort count of non-ignored files, capped for responsiveness."""

    n = 0
    for _ in walk_files(root, ignore, limits=limits, max_files=cap):
        n += 1
    return n
