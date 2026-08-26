"""Code-intelligence layer: read-only, bounded, containment-checked access to
repositories behind a single :class:`RepositoryInterface`.

Functional today: the local adapter (Phases 0–3).
Scaffolded: the GitHub adapter and the deferred code-graph capabilities.
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
from .github_adapter import GitHubRepositoryAdapter
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
    "GitHubRepositoryAdapter",
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
