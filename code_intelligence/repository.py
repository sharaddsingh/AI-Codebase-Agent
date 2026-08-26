"""The single repository abstraction the rest of the system programs against.

The agent, MCP server, and API never contain local-vs-GitHub branching: they
hold a :class:`RepositoryInterface` and call the same methods regardless of
where the code physically lives.  :class:`LocalRepositoryAdapter` serves a local
filesystem path; :class:`~code_intelligence.github_mcp_repository.GitHubMCPRepository`
serves a GitHub repository through the official GitHub MCP server (remote,
read-only).  Both are fully functional and can coexist in one session.

The four *implemented* capabilities are abstract (every adapter must provide
them).  The three *deferred* capabilities (``find_symbol``, ``find_references``,
``get_dependencies``) have concrete implementations that raise
:class:`NotSupportedError` — they define the eventual surface without pretending
it exists yet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .errors import NotSupportedError
from .models import (
    DirectoryListing,
    FileContent,
    FileMetadata,
    RepositoryKind,
    RepoSnapshot,
    SearchResults,
)


class RepositoryInterface(ABC):
    """Read-only access to one repository at a specific snapshot."""

    id: str
    kind: RepositoryKind
    display_name: str

    # ---- Snapshot / version identity ------------------------------------
    @abstractmethod
    def get_snapshot(self) -> RepoSnapshot:
        """Return the version identifier for the repository's current state."""

    # ---- Implemented capabilities (Phase 0–3) ---------------------------
    @abstractmethod
    def list_files(
        self, path: str = "", *, page: int = 1, page_size: int | None = None
    ) -> DirectoryListing:
        """List the immediate children of a directory (paginated, ignore-aware)."""

    @abstractmethod
    def read_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        max_bytes: int | None = None,
    ) -> FileContent:
        """Read a bounded slice of a text file."""

    @abstractmethod
    def search_code(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        path_glob: str | None = None,
        max_results: int | None = None,
    ) -> SearchResults:
        """Lexically search file contents (ripgrep, with a pure-Python fallback)."""

    @abstractmethod
    def get_file_metadata(self, path: str) -> FileMetadata:
        """Return size, line count, language, binary flag, mtime, and sha256."""

    # ---- Deferred capabilities (documented, not yet built) --------------
    # These define the target surface for the code-graph phase.  They raise a
    # distinct NotSupportedError so callers can tell "not built yet" apart from
    # "bad request", and so the UI can advertise them as roadmap items.

    def find_symbol(self, name: str, *, kind: str | None = None) -> object:
        raise NotSupportedError(
            "find_symbol is deferred to the Tree-sitter AST phase "
            "(symbols, references, imports, code graph)."
        )

    def find_references(self, path: str, line: int, column: int) -> object:
        raise NotSupportedError(
            "find_references is deferred to the Tree-sitter AST phase."
        )

    def get_dependencies(self, path: str) -> object:
        raise NotSupportedError(
            "get_dependencies is deferred to the Tree-sitter AST / code-graph phase."
        )
