"""Typed, serializable models shared across the engine, agent, MCP server, and API.

These are Pydantic models so they can be validated once and reused as HTTP
response bodies, MCP tool outputs, and the JSON that is handed to the LLM.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RepositoryKind(str, Enum):
    local = "local"
    github = "github"


class FileType(str, Enum):
    file = "file"
    dir = "dir"
    symlink = "symlink"
    other = "other"


class RepoSnapshot(BaseModel):
    """A version identifier for a repository's state.

    Citations, retrieval indexes, and (future) patches are tied to a snapshot
    so that an answer can be reproduced against the exact code it was based on.
    For a git working tree the id is derived from the commit sha; otherwise it
    is a content/time-derived id captured at registration.
    """

    id: str = Field(description="Stable id for this snapshot, e.g. 'git:1a2b3c4d' or 'wt:...'.")
    kind: str = Field(default="working-tree", description="'git' or 'working-tree'.")
    revision: str | None = Field(default=None, description="Git commit sha when available.")
    dirty: bool = Field(default=False, description="Working tree has uncommitted changes.")
    captured_at: datetime


class RepositoryInfo(BaseModel):
    """Public-facing repository descriptor.

    ``root`` is the server-side absolute path.  The API layer decides whether to
    surface it; it is never sent to the browser as something the user can edit
    into a traversal.
    """

    id: str
    name: str
    kind: RepositoryKind
    root: str
    snapshot: RepoSnapshot
    registered_at: datetime
    file_count_hint: int | None = Field(
        default=None, description="Approximate number of non-ignored files (best effort)."
    )


class FileEntry(BaseModel):
    path: str = Field(description="Repository-relative POSIX path.")
    name: str
    type: FileType
    size: int | None = Field(default=None, description="Size in bytes for files.")


class DirectoryListing(BaseModel):
    repo_id: str
    path: str
    entries: list[FileEntry]
    total: int = Field(description="Total non-ignored entries in this directory before pagination.")
    page: int
    page_size: int
    truncated: bool = Field(description="True when more entries exist beyond this page.")


class FileContent(BaseModel):
    repo_id: str
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    truncated: bool
    encoding: str
    bytes_returned: int


class FileMetadata(BaseModel):
    repo_id: str
    path: str
    size_bytes: int
    line_count: int | None = Field(default=None, description="None for binary files.")
    language: str | None = None
    is_binary: bool = False
    modified_at: datetime
    sha256: str


class SearchMatch(BaseModel):
    path: str = Field(description="Repository-relative POSIX path.")
    line_number: int
    line: str = Field(description="The matching line, bounded in length.")
    context: str | None = Field(default=None, description="Optional surrounding lines.")


class SearchResults(BaseModel):
    repo_id: str
    query: str
    matches: list[SearchMatch]
    total_matches: int
    truncated: bool
    engine: str = Field(description="'ripgrep', 'python-fallback', or 'github-mcp'.")
    notes: str | None = Field(
        default=None,
        description=(
            "Human-readable coverage caveat when the search did not scan the whole "
            "repository (e.g. GitHub bounded a subset of files). Absent when the "
            "search was exhaustive."
        ),
    )


class Citation(BaseModel):
    """A file/line reference backing part of an answer, pinned to a snapshot."""

    path: str
    start_line: int
    end_line: int
    snapshot_id: str | None = None
