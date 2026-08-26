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
    (e.g. ``find_symbol`` on the local adapter).  Using a distinct error keeps
    "not built yet" clearly separate from "bad request".
    """

    code = "not_supported"
    http_status = 501


# ---- GitHub-over-MCP source errors ----------------------------------------
# These describe failures registering or reading a GitHub repository through the
# official GitHub MCP server.  Their messages are user-facing and deliberately
# generic: they never echo the token, an Authorization header, the MCP endpoint
# URL, or a raw GitHub/MCP response body.


class InvalidGitHubUrlError(CodeIntelError):
    """The supplied string was routed to GitHub but is not a usable repo URL."""

    code = "invalid_github_url"
    http_status = 400


class GitHubMCPConnectionError(CodeIntelError):
    """Could not establish a session with the GitHub MCP server."""

    code = "github_mcp_connection_failed"
    http_status = 502


class GitHubMCPUnavailableError(CodeIntelError):
    """The GitHub MCP server is unusable for read-only investigation.

    Raised when the server advertises a write tool while read-only mode was
    requested, or when the expected read tools are missing — the client fails
    closed rather than proceeding against a server that could mutate a repo.
    """

    code = "github_mcp_unavailable"
    http_status = 502


class GitHubMCPAuthError(CodeIntelError):
    """The GitHub MCP server rejected the request for authentication reasons.

    Typically a missing/invalid ``GITHUB_TOKEN`` or a token lacking the scope the
    remote server requires (it mandates a token even for public repositories).
    """

    code = "github_mcp_authentication_failed"
    http_status = 401


class GitHubMCPToolError(CodeIntelError):
    """A GitHub MCP tool call returned an error result or a malformed payload."""

    code = "github_mcp_tool_error"
    http_status = 502


class GitHubRepoNotFoundError(CodeIntelError):
    """The GitHub repository, path, or ref does not exist (or is not visible to
    the configured token)."""

    code = "github_repository_not_found"
    http_status = 404


class GitHubRepoAccessDeniedError(CodeIntelError):
    """The configured token is not permitted to access the GitHub repository."""

    code = "github_repository_access_denied"
    http_status = 403
