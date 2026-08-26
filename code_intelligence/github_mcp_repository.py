"""GitHub implementation of :class:`RepositoryInterface`, backed by the official
GitHub MCP server.

Every capability is expressed as a **generic repository operation** and translated
into one or more **GitHub MCP tool calls** through a :class:`GitHubMCPClient`.  The
agent, API, and MCP-server surfaces never learn that a repository is remote — they
call the same five methods they call on the local adapter.

Registration snapshots the repository once: the newest commit on the default
branch (``list_commits``) pins a revision, and the recursive tree
(``get_repository_tree``) is cached in memory so ``list_files`` is a pure lookup.
File bytes are fetched lazily and cached, sha-pinned to that revision, via
``get_file_contents``.  Search delegates to the MCP ``search_code`` tool and is
**honest** about GitHub's coverage limits (default-branch only, no reliable line
numbers, no regex) rather than fabricating precision.

Path safety uses only :func:`normalize_relative` (a pure-string check that rejects
absolute/drive/``..``/NUL paths) — never a filesystem containment helper, because
nothing here touches disk.
"""

from __future__ import annotations

import base64
import binascii
import json
import posixpath
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ResourceLink,
    TextContent,
    TextResourceContents,
)

from .content import build_metadata_from_bytes, guard_binary, slice_text_content
from .errors import (
    BinaryFileError,
    FileTooLargeError,
    GitHubMCPToolError,
    GitHubRepoNotFoundError,
    NotADirError,
    NotAFileError,
    PathNotFoundError,
    SearchError,
)
from .github_mcp_client import GitHubMCPClient, MCPToolResult
from .ignore import IgnoreRules
from .languages import is_binary_ext
from .limits import DEFAULT_LIMITS, EngineLimits
from .models import (
    DirectoryListing,
    FileContent,
    FileEntry,
    FileMetadata,
    FileType,
    RepositoryKind,
    RepoSnapshot,
    SearchMatch,
    SearchResults,
)
from .paths import normalize_relative
from .repository import RepositoryInterface


@dataclass(frozen=True)
class _Blob:
    sha: str
    size: int


def _parse_commit_date(commit: dict[str, Any]) -> datetime | None:
    try:
        c = commit.get("commit") or {}
        info = c.get("committer") or c.get("author") or {}
        raw = info.get("date")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (AttributeError, ValueError, TypeError):
        return None


def _extract_commits(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        for key in ("commits", "items", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return [c for c in v if isinstance(c, dict)]
        if "sha" in data:
            return [data]
    return []


def _extract_tree(data: Any) -> tuple[list[dict[str, Any]], bool]:
    if isinstance(data, dict):
        truncated = bool(data.get("truncated", False))
        for key in ("tree", "entries", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return [e for e in v if isinstance(e, dict)], truncated
        return [], truncated
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)], False
    return [], False


class GitHubMCPRepository(RepositoryInterface):
    """Read-only access to a GitHub repository through the GitHub MCP server."""

    kind = RepositoryKind.github

    def __init__(
        self,
        repo_id: str,
        owner: str,
        repo: str,
        *,
        client: GitHubMCPClient,
        limits: EngineLimits = DEFAULT_LIMITS,
    ) -> None:
        self.id = repo_id
        self.owner = owner
        self.repo = repo
        self.display_name = f"{owner}/{repo}"
        self._client = client
        self._limits = limits
        # Rootless ignore rules so node_modules/.git/dist/... hide exactly as they
        # do for a local repo (no filesystem, no .gitignore).
        self._ignore = IgnoreRules()
        self._files: dict[str, _Blob] = {}
        self._dirs: set[str] = set()
        self._content_cache: dict[str, bytes] = {}
        self._revision: str | None = None
        self._commit_date: datetime | None = None
        self._tree_truncated = False
        self._snapshot: RepoSnapshot | None = None
        self._load()

    # ---- registration / snapshot ---------------------------------------- #
    def _args(self, **extra: Any) -> dict[str, Any]:
        return {"owner": self.owner, "repo": self.repo, **extra}

    def _load(self) -> None:
        commits = _extract_commits(
            self._client.call_tool("list_commits", self._args(perPage=1)).json()
        )
        if not commits:
            raise GitHubRepoNotFoundError(
                "The GitHub repository has no commits or could not be found."
            )
        head = commits[0]
        self._revision = str(head.get("sha") or "") or None
        self._commit_date = _parse_commit_date(head)
        if not self._revision:
            raise GitHubMCPToolError("The GitHub MCP server returned a commit without a sha.")

        entries, truncated = _extract_tree(
            self._client.call_tool(
                "get_repository_tree",
                self._args(tree_sha=self._revision, recursive=True),
            ).json()
        )
        self._tree_truncated = truncated
        for entry in entries:
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                continue
            etype = str(entry.get("type") or "").lower()
            if etype in ("blob", "file"):
                if self._ignore.is_ignored(path, False):
                    continue
                size = entry.get("size")
                self._files[path] = _Blob(
                    sha=str(entry.get("sha") or ""),
                    size=int(size) if isinstance(size, (int, float)) else 0,
                )
                self._add_ancestors(path)
            elif etype in ("tree", "dir", "directory"):
                if self._ignore.is_ignored(path, True):
                    continue
                self._dirs.add(path)
                self._add_ancestors(path)

        self._snapshot = RepoSnapshot(
            id=f"gh:{self._revision[:12]}",
            kind="github",
            revision=self._revision,
            dirty=False,
            captured_at=datetime.now(tz=timezone.utc),
        )

    def _add_ancestors(self, path: str) -> None:
        parent = posixpath.dirname(path)
        while parent:
            self._dirs.add(parent)
            parent = posixpath.dirname(parent)

    @property
    def file_count(self) -> int:
        return len(self._files)

    @property
    def tree_truncated(self) -> bool:
        return self._tree_truncated

    def get_snapshot(self) -> RepoSnapshot:
        assert self._snapshot is not None  # set in _load()
        return self._snapshot

    # ---- listing --------------------------------------------------------- #
    def list_files(
        self, path: str = "", *, page: int = 1, page_size: int | None = None
    ) -> DirectoryListing:
        rel = normalize_relative(path)
        if rel and rel not in self._dirs:
            if rel in self._files:
                raise NotADirError(f"Not a directory: {rel}")
            raise PathNotFoundError(f"Directory not found: {rel}")

        entries: list[FileEntry] = [
            FileEntry(path=d, name=posixpath.basename(d), type=FileType.dir, size=None)
            for d in self._dirs
            if posixpath.dirname(d) == rel
        ]
        entries += [
            FileEntry(path=f, name=posixpath.basename(f), type=FileType.file, size=blob.size)
            for f, blob in self._files.items()
            if posixpath.dirname(f) == rel
        ]
        # Directories first, then files, each alphabetical (case-insensitive) —
        # identical ordering to engine.build_directory_listing.
        entries.sort(key=lambda e: (e.type != FileType.dir, e.name.lower()))

        page = max(1, page)
        size = page_size or self._limits.default_page_size
        size = max(1, min(size, self._limits.max_page_size))
        total = len(entries)
        start = (page - 1) * size
        end = start + size
        return DirectoryListing(
            repo_id=self.id,
            path=rel,
            entries=entries[start:end],
            total=total,
            page=page,
            page_size=size,
            truncated=end < total,
        )

    # ---- reading --------------------------------------------------------- #
    def _require_file(self, rel: str) -> _Blob:
        if rel == "":
            raise NotAFileError("Path is a directory, not a file: (root)")
        blob = self._files.get(rel)
        if blob is None:
            if rel in self._dirs:
                raise NotAFileError(f"Path is a directory, not a file: {rel}")
            raise PathNotFoundError(f"File not found: {rel}")
        return blob

    def read_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        max_bytes: int | None = None,
    ) -> FileContent:
        rel = normalize_relative(path)
        blob = self._require_file(rel)

        name = posixpath.basename(rel)
        if is_binary_ext(name):
            raise BinaryFileError(f"Refusing to read binary file: {rel}")
        # Refuse oversize files BEFORE downloading them, using the tree's size.
        if blob.size > self._limits.max_readable_file_bytes:
            raise FileTooLargeError(
                f"File is {blob.size} bytes; exceeds the readable limit of "
                f"{self._limits.max_readable_file_bytes} bytes: {rel}"
            )

        raw = self._get_content(rel, blob)
        guard_binary(rel, raw[: self._limits.binary_sniff_bytes], limits=self._limits)
        # file_truncated=False: we downloaded the whole (size-checked) blob; any
        # truncation from here is line/byte budgeting handled by slice_text_content.
        return slice_text_content(
            self.id,
            rel,
            raw,
            file_truncated=False,
            start_line=start_line,
            end_line=end_line,
            max_bytes=max_bytes,
            limits=self._limits,
        )

    def get_file_metadata(self, path: str) -> FileMetadata:
        rel = normalize_relative(path)
        blob = self._require_file(rel)
        raw = self._get_content(rel, blob)
        return build_metadata_from_bytes(
            self.id,
            rel,
            raw,
            modified_at=self._commit_date,
            size_bytes=blob.size,
            limits=self._limits,
        )

    def _get_content(self, rel: str, blob: _Blob) -> bytes:
        cached = self._content_cache.get(rel)
        if cached is not None:
            return cached
        result = self._client.call_tool(
            "get_file_contents", self._args(path=rel, ref=self._revision)
        )
        raw = self._content_from_result(result, rel)
        self._content_cache[rel] = raw
        return raw

    def _content_from_result(self, result: MCPToolResult, rel: str) -> bytes:
        for block in result.content:
            if isinstance(block, EmbeddedResource):
                res = block.resource
                if isinstance(res, BlobResourceContents) and res.blob:
                    return _b64(res.blob, rel)
                if isinstance(res, TextResourceContents) and res.text is not None:
                    return res.text.encode("utf-8")
            elif isinstance(block, ResourceLink):
                # Content was not inlined (typically too large to embed).
                raise FileTooLargeError(f"File is too large to read inline: {rel}")

        texts = [b.text for b in result.content if isinstance(b, TextContent)]
        if len(texts) == 1:
            wrapped = _maybe_rest_wrapper(texts[0])
            return wrapped if wrapped is not None else texts[0].encode("utf-8")
        if len(texts) > 1:
            return "".join(texts).encode("utf-8")

        wrapped = _structured_wrapper(result.structured)
        if wrapped is not None:
            return wrapped
        raise GitHubMCPToolError(
            f"The GitHub MCP server returned no readable content for {rel!r}."
        )

    # ---- search ---------------------------------------------------------- #
    def search_code(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        path_glob: str | None = None,
        max_results: int | None = None,
    ) -> SearchResults:
        q = (query or "").strip()
        if not q:
            raise SearchError("Search query must not be empty.")
        if len(q) > self._limits.max_query_length:
            raise SearchError(
                f"Search query is too long (max {self._limits.max_query_length} characters)."
            )

        cap = min(max_results or self._limits.max_search_results, self._limits.max_search_results)
        gh_query = f"repo:{self.owner}/{self.repo} {q}"

        try:
            data = self._client.call_tool(
                "search_code", {"query": gh_query, "perPage": cap}
            ).json()
        except SearchError:
            raise
        except GitHubMCPToolError as exc:
            # Degrade gracefully: search must never derail the agent. Exact
            # citations still come from read_file.
            return SearchResults(
                repo_id=self.id,
                query=query,
                matches=[],
                total_matches=0,
                truncated=True,
                engine="github-mcp",
                notes=_search_notes(regex, path_glob, degraded=exc.message),
            )

        items, total, incomplete = _extract_search(data)
        matches: list[SearchMatch] = []
        for item in items[:cap]:
            path = item.get("path") or item.get("name")
            if not isinstance(path, str) or not path:
                continue
            line = _representative_line(item, self._limits.max_line_length)
            # GitHub code search does NOT return reliable line numbers; we use 1
            # and disclose this in `notes` rather than fabricate a position.
            matches.append(SearchMatch(path=path, line_number=1, line=line, context=None))

        truncated = bool(incomplete) or total > len(matches)
        return SearchResults(
            repo_id=self.id,
            query=query,
            matches=matches,
            total_matches=total or len(matches),
            truncated=truncated,
            engine="github-mcp",
            notes=_search_notes(regex, path_glob, degraded=None),
        )


# --------------------------------------------------------------------------- #
# Module helpers                                                              #
# --------------------------------------------------------------------------- #
def _b64(data: str, rel: str) -> bytes:
    try:
        return base64.b64decode(data)
    except (binascii.Error, ValueError) as exc:
        raise GitHubMCPToolError(
            f"The GitHub MCP server returned undecodable content for {rel!r}."
        ) from exc


def _maybe_rest_wrapper(text: str) -> bytes | None:
    """Decode a REST-style ``{"content": ..., "encoding": ...}`` blob if that is
    what the server returned; otherwise ``None`` (the text is the file itself)."""

    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return _structured_wrapper(obj)


def _structured_wrapper(obj: Any) -> bytes | None:
    if not isinstance(obj, dict):
        return None
    content = obj.get("content")
    if not isinstance(content, str) or "encoding" not in obj:
        return None
    if obj.get("encoding") == "base64":
        try:
            return base64.b64decode(content)
        except (binascii.Error, ValueError):
            return None
    return content.encode("utf-8")


def _extract_search(data: Any) -> tuple[list[dict[str, Any]], int, bool]:
    if isinstance(data, dict):
        for key in ("items", "results", "matches"):
            v = data.get(key)
            if isinstance(v, list):
                items = [i for i in v if isinstance(i, dict)]
                total = data.get("total_count")
                if not isinstance(total, int):
                    total = data.get("total") if isinstance(data.get("total"), int) else len(items)
                return items, int(total), bool(data.get("incomplete_results", False))
        return [], 0, False
    if isinstance(data, list):
        items = [i for i in data if isinstance(i, dict)]
        return items, len(items), False
    return [], 0, False


def _representative_line(item: dict[str, Any], max_len: int) -> str:
    text_matches = item.get("text_matches")
    if isinstance(text_matches, list):
        for tm in text_matches:
            if isinstance(tm, dict):
                fragment = tm.get("fragment")
                if isinstance(fragment, str) and fragment.strip():
                    first = next((ln for ln in fragment.splitlines() if ln.strip()), "")
                    return first[:max_len]
    return ""


def _search_notes(regex: bool, path_glob: str | None, *, degraded: str | None) -> str:
    parts = [
        "GitHub code search covers the repository's default branch only, uses "
        "GitHub query semantics, and does not return reliable line numbers "
        "(reported as 1); use read_file for exact line citations."
    ]
    if regex:
        parts.append(
            "Regex was requested, but GitHub code search does not support regex; "
            "the query was treated literally."
        )
    if path_glob:
        parts.append(
            f"path_glob {path_glob!r} was not applied (GitHub search uses different "
            "path qualifiers)."
        )
    if degraded:
        parts.append(f"Search was degraded and returned no results: {degraded}")
    return " ".join(parts)
