"""Typed errors for the code-intelligence layer.

Every error carries a stable machine ``code`` and a safe, user-presentable
message.  The backend maps ``http_status`` onto HTTP responses; the MCP server
maps ``code`` onto structured tool errors.  Messages must never leak secrets or
absolute host paths that the caller did not already supply.
"""

from __future__ import annotations


class CodeIntelError(Exception):
    """Base class for all code-intelligence errors."""

    code: str = "code_intel_error"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class PathValidationError(CodeIntelError):
    """A path was absolute, escaped the repository root, or was otherwise unsafe."""

    code = "path_validation_error"
    http_status = 400


class RepositoryNotFoundError(CodeIntelError):
    """The requested repository id is not registered."""

    code = "repository_not_found"
    http_status = 404


class PathNotFoundError(CodeIntelError):
    """The resolved path does not exist inside the repository."""

    code = "path_not_found"
    http_status = 404


class NotAFileError(CodeIntelError):
    code = "not_a_file"
    http_status = 400


class NotADirError(CodeIntelError):
    code = "not_a_directory"
    http_status = 400


class FileTooLargeError(CodeIntelError):
    code = "file_too_large"
    http_status = 413


class BinaryFileError(CodeIntelError):
    code = "binary_file"
    http_status = 415


class SearchError(CodeIntelError):
    code = "search_error"
    http_status = 400


class RegistrationError(CodeIntelError):
    """The path supplied for repository registration was rejected."""

    code = "registration_error"
    http_status = 400


class NotSupportedError(CodeIntelError):
    """A capability that is intentionally deferred to a later phase.

    Raised by interface methods that are documented but not yet implemented
    (e.g. ``find_symbol`` on the local adapter, or anything on the GitHub
    placeholder).  Using a distinct error keeps "not built yet" clearly
    separate from "bad request".
    """

    code = "not_supported"
    http_status = 501
