"""Pure byte→model helpers shared by the local and GitHub adapters.

Reading a file means the same thing regardless of where the bytes came from: the
local adapter reads them from disk, the GitHub adapter fetches them from the blob
API, and both then produce an identical, bounded :class:`FileContent` /
:class:`FileMetadata`. Centralizing that logic here keeps the two sources
behaviorally identical — the slicing rules (line window, per-call byte budget,
truncation flags, trailing-newline handling) live in exactly one place.

Nothing here touches the filesystem or the network; callers supply the bytes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from .errors import BinaryFileError
from .languages import guess_language, is_binary_ext, looks_binary
from .limits import DEFAULT_LIMITS, EngineLimits
from .models import FileContent, FileMetadata


def _basename(rel_posix: str) -> str:
    return rel_posix.rsplit("/", 1)[-1]


def guard_binary(rel_posix: str, sample: bytes, *, limits: EngineLimits = DEFAULT_LIMITS) -> None:
    """Raise :class:`BinaryFileError` if the path or a content sniff looks binary.

    ``sample`` should be the leading bytes of the content (the caller may pass the
    whole content when it is already in memory).
    """

    if is_binary_ext(_basename(rel_posix)) or looks_binary(sample[: limits.binary_sniff_bytes]):
        raise BinaryFileError(f"Refusing to read binary file: {rel_posix}")


def slice_text_content(
    repo_id: str,
    rel_posix: str,
    raw: bytes,
    *,
    file_truncated: bool,
    start_line: int | None = None,
    end_line: int | None = None,
    max_bytes: int | None = None,
    limits: EngineLimits = DEFAULT_LIMITS,
) -> FileContent:
    """Decode ``raw`` and return a bounded line-window as :class:`FileContent`.

    ``raw`` must already be capped at ``limits.max_readable_file_bytes`` by the
    caller; ``file_truncated`` says whether that cap dropped trailing bytes. The
    returned slice honors the ``start_line``/``end_line`` window and the per-call
    ``max_bytes`` (bounded by ``limits.max_read_bytes``), and reports ``truncated``
    when any of those cut the result short.
    """

    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    # A trailing newline yields a spurious empty final element; drop it.
    if lines and lines[-1] == "":
        lines.pop()
    total_lines = len(lines)

    s = max(1, start_line or 1)
    e = end_line or total_lines
    e = max(s, min(e, total_lines)) if total_lines else s

    ceiling = limits.max_read_bytes
    budget = min(max_bytes or ceiling, ceiling)

    out: list[str] = []
    used = 0
    last_line = s - 1
    truncated_by_bytes = False
    for i in range(s, e + 1):
        if i - 1 >= total_lines:
            break
        piece = lines[i - 1]
        cost = len(piece.encode("utf-8")) + 1
        if out and used + cost > budget:
            truncated_by_bytes = True
            break
        out.append(piece)
        used += cost
        last_line = i

    content = "\n".join(out)
    truncated = truncated_by_bytes or file_truncated or last_line < e
    return FileContent(
        repo_id=repo_id,
        path=rel_posix,
        start_line=s if total_lines else 0,
        end_line=last_line,
        total_lines=total_lines,
        content=content,
        truncated=truncated,
        encoding="utf-8",
        bytes_returned=len(content.encode("utf-8")),
    )


def build_metadata_from_bytes(
    repo_id: str,
    rel_posix: str,
    raw: bytes,
    *,
    modified_at: datetime,
    size_bytes: int | None = None,
    limits: EngineLimits = DEFAULT_LIMITS,
) -> FileMetadata:
    """Compute :class:`FileMetadata` from in-memory content bytes.

    Used by the GitHub adapter, which already has the blob bytes in hand. The
    local adapter keeps its own streaming implementation (it never loads a whole
    large file just to hash it). ``size_bytes`` overrides ``len(raw)`` when the
    true size is known from a source of truth (e.g. the git tree).
    """

    size = size_bytes if size_bytes is not None else len(raw)
    is_bin = is_binary_ext(_basename(rel_posix)) or looks_binary(raw[: limits.binary_sniff_bytes])

    line_count: int | None = None
    if not is_bin:
        newlines = raw.count(b"\n")
        last_byte = raw[-1:] if raw else b""
        line_count = newlines + (1 if size > 0 and last_byte != b"\n" else 0)

    return FileMetadata(
        repo_id=repo_id,
        path=rel_posix,
        size_bytes=size,
        line_count=line_count,
        language=guess_language(_basename(rel_posix)),
        is_binary=is_bin,
        modified_at=modified_at,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
