"""GitHub repository adapter — NON-FUNCTIONAL placeholder.

This class deliberately does not work yet.  It exists so the rest of the system
can be written against :class:`RepositoryInterface` with a concrete second
implementation in mind, and so the roadmap is expressed in code rather than
only in prose.  Instantiating it or calling any method raises
:class:`NotSupportedError`.

Planned design (later phase — "GitHub repository adapter via GitHub MCP"):

* Construction from ``owner``, ``repo`` and a ``ref`` (branch / tag / commit).
* Authentication via a **server-side** token (e.g. ``GITHUB_TOKEN``) that is
  never sent to the browser — identical secret-handling posture to the model
  provider key.
* Snapshot identity = the resolved commit sha, so citations produced against a
  GitHub repo pin to an immutable commit just like the local adapter pins to a
  working-tree / git snapshot.
* Two viable backends, both behind this same interface:
    1. The official **GitHub MCP server** proxied as tools, or
    2. A scoped **GitHub REST/GraphQL** client (contents API + code search).
* The eventual capability surface matches the interface, including the deferred
  ``find_symbol`` / ``find_references`` / ``get_dependencies``.
"""

from __future__ import annotations

from .errors import NotSupportedError
from .models import (
    DirectoryListing,
    FileContent,
    FileMetadata,
    RepositoryKind,
    RepoSnapshot,
    SearchResults,
)
from .repository import RepositoryInterface

_MSG = (
    "The GitHub repository adapter is not implemented yet. It is scaffolded for "
    "a later phase (GitHub MCP or a scoped GitHub API adapter). Use a local "
    "repository for now."
)


class GitHubRepositoryAdapter(RepositoryInterface):
    kind = RepositoryKind.github

    def __init__(self, owner: str, repo: str, ref: str = "HEAD", *, token: str | None = None) -> None:
        # Intentionally refuse construction so this can never be mistaken for a
        # working adapter. The signature documents the intended inputs.
        raise NotSupportedError(_MSG)

    def get_snapshot(self) -> RepoSnapshot:  # pragma: no cover - unreachable
        raise NotSupportedError(_MSG)

    def list_files(
        self, path: str = "", *, page: int = 1, page_size: int | None = None
    ) -> DirectoryListing:  # pragma: no cover - unreachable
        raise NotSupportedError(_MSG)

    def read_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        max_bytes: int | None = None,
    ) -> FileContent:  # pragma: no cover - unreachable
        raise NotSupportedError(_MSG)

    def search_code(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        path_glob: str | None = None,
        max_results: int | None = None,
    ) -> SearchResults:  # pragma: no cover - unreachable
        raise NotSupportedError(_MSG)

    def get_file_metadata(self, path: str) -> FileMetadata:  # pragma: no cover - unreachable
        raise NotSupportedError(_MSG)
