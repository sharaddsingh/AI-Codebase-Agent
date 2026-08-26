"""Lexical code search: ripgrep when available, pure-Python fallback otherwise.

Security notes:

* The query is passed to ripgrep via ``-e <query>`` and the root via ``-- <root>``
  using an argument **list** (``shell=False``); the query is never interpolated
  into a shell command, so it cannot inject flags or commands.
* Results are bounded (per-file cap, global cap, byte-per-line cap) and the
  whole search is deadline-limited; a pathological query cannot hang or flood.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from code_intelligence.engine import walk_files
from code_intelligence.errors import SearchError
from code_intelligence.ignore import DEFAULT_IGNORE_DIRS, IgnoreRules
from code_intelligence.languages import is_binary_ext, looks_binary
from code_intelligence.limits import DEFAULT_LIMITS, EngineLimits
from code_intelligence.models import SearchMatch, SearchResults
from code_intelligence.paths import to_relative_posix


def _truncate_line(text: str, max_len: int) -> str:
    text = text.rstrip("\n").rstrip("\r")
    if len(text) > max_len:
        return text[:max_len] + " …[truncated]"
    return text


def _validate_query(query: str, limits: EngineLimits) -> str:
    q = (query or "").strip()
    if not q:
        raise SearchError("Search query must not be empty.")
    if len(q) > limits.max_query_length:
        raise SearchError(f"Search query exceeds {limits.max_query_length} characters.")
    return q


def ripgrep_available() -> bool:
    return shutil.which("rg") is not None


def _search_ripgrep(
    root: Path,
    ignore: IgnoreRules,
    query: str,
    *,
    regex: bool,
    case_sensitive: bool,
    path_glob: str | None,
    max_results: int,
    limits: EngineLimits,
    repo_id: str,
) -> SearchResults:
    rg = shutil.which("rg")
    assert rg is not None
    args: list[str] = [
        rg,
        "--json",
        "--line-number",
        "--max-count",
        str(limits.max_search_per_file),
        "--max-filesize",
        str(limits.max_search_filesize),
        "--hidden",  # include dotfiles like .github/, but...
    ]
    # ...exclude our standard ignore directories explicitly.
    for d in sorted(DEFAULT_IGNORE_DIRS):
        args += ["--glob", f"!**/{d}/**", "--glob", f"!{d}/**"]
    if not regex:
        args.append("--fixed-strings")
    if not case_sensitive:
        args.append("--ignore-case")
    if path_glob:
        if len(path_glob) > 200:
            raise SearchError("path_glob is too long.")
        args += ["--glob", path_glob]
    args += ["-e", query, "--", str(root)]

    matches: list[SearchMatch] = []
    truncated = False
    deadline = time.monotonic() + limits.search_timeout_s
    proc = subprocess.Popen(  # noqa: S603 - args is a fixed list, shell=False
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(root),
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if time.monotonic() > deadline:
                truncated = True
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "match":
                continue
            data = obj["data"]
            path_obj = data.get("path", {})
            if "text" not in path_obj:
                continue  # non-UTF8 path; skip
            rel = to_relative_posix(root, Path(path_obj["text"]))
            if ignore.is_ignored(rel, False):
                continue
            lines_obj = data.get("lines", {})
            text = lines_obj.get("text", "")
            matches.append(
                SearchMatch(
                    path=rel,
                    line_number=int(data.get("line_number", 0)),
                    line=_truncate_line(text, limits.max_line_length),
                )
            )
            if len(matches) >= max_results:
                truncated = True
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()

    return SearchResults(
        repo_id=repo_id,
        query=query,
        matches=matches,
        total_matches=len(matches),
        truncated=truncated,
        engine="ripgrep",
    )


def _search_python(
    root: Path,
    ignore: IgnoreRules,
    query: str,
    *,
    regex: bool,
    case_sensitive: bool,
    path_glob: str | None,
    max_results: int,
    limits: EngineLimits,
    repo_id: str,
) -> SearchResults:
    from fnmatch import fnmatch

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query if regex else re.escape(query), flags)
    except re.error as exc:
        raise SearchError(f"Invalid regular expression: {exc}") from exc

    matches: list[SearchMatch] = []
    truncated = False
    deadline = time.monotonic() + limits.search_timeout_s

    for rel, abs_path in walk_files(root, ignore, limits=limits):
        if time.monotonic() > deadline:
            truncated = True
            break
        if path_glob and not fnmatch(rel, path_glob):
            continue
        if is_binary_ext(abs_path.name):
            continue
        try:
            if abs_path.stat().st_size > limits.max_search_filesize:
                continue
            with open(abs_path, "rb") as fh:
                sniff = fh.read(limits.binary_sniff_bytes)
                if looks_binary(sniff):
                    continue
                fh.seek(0)
                raw = fh.read(limits.max_search_filesize)
        except OSError:
            continue

        text = raw.decode("utf-8", errors="replace")
        per_file = 0
        for i, ln in enumerate(text.split("\n"), start=1):
            if pattern.search(ln):
                matches.append(
                    SearchMatch(
                        path=rel,
                        line_number=i,
                        line=_truncate_line(ln, limits.max_line_length),
                    )
                )
                per_file += 1
                if len(matches) >= max_results:
                    truncated = True
                    break
                if per_file >= limits.max_search_per_file:
                    break
        if truncated:
            break

    return SearchResults(
        repo_id=repo_id,
        query=query,
        matches=matches,
        total_matches=len(matches),
        truncated=truncated,
        engine="python-fallback",
    )


def search(
    root: Path,
    ignore: IgnoreRules,
    query: str,
    *,
    regex: bool = False,
    case_sensitive: bool = False,
    path_glob: str | None = None,
    max_results: int | None = None,
    limits: EngineLimits = DEFAULT_LIMITS,
    repo_id: str = "",
) -> SearchResults:
    """Search file contents under ``root``. Prefers ripgrep; falls back to Python."""

    q = _validate_query(query, limits)
    cap = max(1, min(max_results or limits.max_search_results, limits.max_search_results))
    impl = _search_ripgrep if ripgrep_available() else _search_python
    return impl(
        root,
        ignore,
        q,
        regex=regex,
        case_sensitive=case_sensitive,
        path_glob=path_glob,
        max_results=cap,
        limits=limits,
        repo_id=repo_id,
    )
