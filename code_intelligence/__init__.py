"""Code-intelligence layer: read-only, bounded, containment-checked access to
repositories behind a single :class:`RepositoryInterface`.

Functional today: the local adapter and the GitHub-over-MCP adapter (Phases 0–3).
Scaffolded: the deferred code-graph capabilities (find_symbol/references/deps).
"""

from .errors import (
    BinaryFileError,
    CodeIntelError,
    FileTooLargeError,
    NotADirError,
    NotAFileError,
    NotSupportedError,
    PathNotFoundError,
    PathValidationError,
    RegistrationError,
    RepositoryNotFoundError,
    SearchError,
)
from .github_mcp_repository import GitHubMCPRepository
from .limits import DEFAULT_LIMITS, EngineLimits
from .local_adapter import LocalRepositoryAdapter
from .models import (
    Citation,
    DirectoryListing,
    FileContent,
    FileEntry,
    FileMetadata,
    FileType,
    RepositoryInfo,
    RepositoryKind,
    RepoSnapshot,
    SearchMatch,
    SearchResults,
)
from .registry import RepositoryRegistry
from .repository import RepositoryInterface

__all__ = [
    # interface + adapters
    "RepositoryInterface",
    "LocalRepositoryAdapter",
    "GitHubMCPRepository",
    "RepositoryRegistry",
    # models
    "Citation",
    "DirectoryListing",
    "FileContent",
    "FileEntry",
    "FileMetadata",
    "FileType",
    "RepoSnapshot",
    "RepositoryInfo",
    "RepositoryKind",
    "SearchMatch",
    "SearchResults",
    # limits
    "DEFAULT_LIMITS",
    "EngineLimits",
    # errors
    "CodeIntelError",
    "PathValidationError",
    "RepositoryNotFoundError",
    "PathNotFoundError",
    "NotAFileError",
    "NotADirError",
    "FileTooLargeError",
    "BinaryFileError",
    "SearchError",
    "RegistrationError",
    "NotSupportedError",
]
