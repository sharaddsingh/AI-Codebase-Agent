"""In-memory registry of authorized repositories.

For the MVP the registry lives in the backend process (no database).  It is the
single place that decides *what* may be registered and *how*: it auto-detects
whether a registration string is a local filesystem path or a GitHub URL
(:meth:`RepositoryRegistry.register`), routes it to the matching adapter, and
hands out :class:`RepositoryInterface` instances by id to the rest of the
system.  Local registration may be constrained to a configured allow-list of
roots; that allow-list is a *filesystem* control and does not apply to GitHub
(which never touches disk).

Registration is idempotent: registering the same real path — or the same
``owner/repo`` — twice returns the same repository id (and refreshes its
snapshot).

Deferred: persistence (PostgreSQL), so repositories and their snapshots survive
restarts and can be shared across workers.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from .engine import count_files
from .errors import RegistrationError, RepositoryNotFoundError
from .github_mcp_client import GitHubMCPClient, RemoteHttpTransport
from .github_mcp_repository import GitHubMCPRepository
from .github_url import canonical_url, looks_like_github, parse_github_url
from .limits import DEFAULT_LIMITS, EngineLimits
from .local_adapter import LocalRepositoryAdapter
from .models import RepositoryInfo, RepositoryKind
from .paths import is_within
from .repository import RepositoryInterface


def _repo_id_for(real_path: str) -> str:
    return "repo_" + hashlib.sha256(os.path.normcase(real_path).encode("utf-8")).hexdigest()[:10]


def _repo_id_for_github(owner: str, repo: str) -> str:
    # Case-insensitive on owner/repo so re-registering the same repo with
    # different casing is idempotent (GitHub names are case-insensitive).
    key = f"github:{owner.lower()}/{repo.lower()}"
    return "repo_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


class RepositoryRegistry:
    def __init__(
        self,
        *,
        allowed_roots: Sequence[str | Path] | None = None,
        respect_gitignore: bool = True,
        limits: EngineLimits = DEFAULT_LIMITS,
        github_token: str | None = None,
        github_mcp_url: str = "https://api.githubcopilot.com/mcp/readonly",
        github_mcp_toolsets: str = "repos,git",
        github_mcp_timeout: float = 30.0,
        github_mcp_client: GitHubMCPClient | None = None,
    ) -> None:
        self._repos: dict[str, RepositoryInterface] = {}
        self._info: dict[str, RepositoryInfo] = {}
        self._respect_gitignore = respect_gitignore
        self._limits = limits
        self._allowed_roots: list[str] = [
            os.path.realpath(str(p)) for p in (allowed_roots or [])
        ]
        # GitHub access flows through the official GitHub MCP server (remote,
        # read-only) authenticated by a server-side PAT. The token is never
        # exposed to the frontend, a response, a citation, a log, or an error;
        # it lives only on the MCP transport's HTTP headers inside the client.
        self._github_token = github_token
        self._github_mcp_url = github_mcp_url
        self._github_mcp_toolsets = github_mcp_toolsets
        self._github_mcp_timeout = github_mcp_timeout
        # A single MCP session (one loop thread) is shared across all GitHub
        # repos; owner/repo are passed as tool arguments. Tests inject a client
        # backed by an in-process fake MCP server so no real network is touched.
        self._github_client = github_mcp_client

    @property
    def allowed_roots(self) -> list[str]:
        return list(self._allowed_roots)

    def _get_github_client(self) -> GitHubMCPClient:
        if self._github_client is None:
            self._github_client = GitHubMCPClient(
                RemoteHttpTransport(
                    self._github_mcp_url,
                    token=self._github_token,
                    toolsets=self._github_mcp_toolsets,
                    timeout=self._github_mcp_timeout,
                ),
                timeout=self._github_mcp_timeout,
            )
        self._github_client.connect()
        return self._github_client

    def close_github_mcp(self) -> None:
        """Close the shared GitHub MCP session and stop its loop thread.

        Called from the FastAPI ``lifespan`` shutdown so a backend restart does
        not leak the loop thread or leave the remote session dangling.
        """

        if self._github_client is not None:
            self._github_client.close()

    def _check_allowed(self, real_path: str) -> None:
        if not self._allowed_roots:
            return  # unrestricted (single-user local dev default)
        for allowed in self._allowed_roots:
            if is_within(allowed, real_path):
                return
        raise RegistrationError(
            "Path is not within an allowed repository root. "
            "Set ALLOWED_REPO_ROOTS to include it, or choose a permitted path."
        )

    def detect_source(self, source: str) -> RepositoryKind:
        """Classify a registration string as a GitHub URL or a local path.

        Detection is by URL *host* (see :func:`looks_like_github`), never a
        substring test, so a local path that merely contains "github.com" is
        still treated as local.
        """

        return RepositoryKind.github if looks_like_github(source) else RepositoryKind.local

    def register(self, source: str, name: str | None = None) -> RepositoryInfo:
        """Register a repository from either a local path or a GitHub URL.

        The source is auto-detected and routed to the matching adapter; local
        registration behavior is unchanged. This is the single entry point the
        API calls so a GitHub URL is never mistaken for a filesystem path.
        """

        if not source or not str(source).strip():
            raise RegistrationError("A repository path or GitHub URL is required.")
        if self.detect_source(source) is RepositoryKind.github:
            return self.register_github(source, name=name)
        return self.register_local(source, name=name)

    def register_local(self, path: str, name: str | None = None) -> RepositoryInfo:
        if not path or not str(path).strip():
            raise RegistrationError("A repository path is required.")
        real = os.path.realpath(str(path))
        real_path = Path(real)
        if not real_path.exists():
            raise RegistrationError(f"Path does not exist: {path}")
        if not real_path.is_dir():
            raise RegistrationError(f"Path is not a directory: {path}")
        self._check_allowed(real)

        repo_id = _repo_id_for(real)
        display = name or real_path.name or repo_id

        adapter = LocalRepositoryAdapter(
            repo_id,
            display,
            real_path,
            respect_gitignore=self._respect_gitignore,
            limits=self._limits,
        )
        info = RepositoryInfo(
            id=repo_id,
            name=display,
            kind=RepositoryKind.local,
            root=str(real_path),
            snapshot=adapter.get_snapshot(),
            registered_at=datetime.now(tz=timezone.utc),
            file_count_hint=count_files(real_path, adapter.ignore, limits=self._limits),
        )
        self._repos[repo_id] = adapter
        self._info[repo_id] = info
        return info

    def register_github(self, url: str, name: str | None = None) -> RepositoryInfo:
        """Register a GitHub repository from a URL (read-only, snapshot-pinned).

        Parsing raises :class:`InvalidGitHubUrlError` for a malformed/deep URL.
        Building the repository opens (lazily, once) the shared GitHub MCP session,
        pins the newest default-branch commit, and fetches the file tree via MCP
        tool calls — surfacing typed MCP-aware errors (connection / auth /
        not-found / tool error), never a raw response or the token. The
        ``allowed_roots`` filesystem allow-list does not apply here — it constrains
        local filesystem access, and GitHub never touches disk.
        """

        owner, repo = parse_github_url(url)
        repo_id = _repo_id_for_github(owner, repo)
        adapter = GitHubMCPRepository(
            repo_id,
            owner,
            repo,
            client=self._get_github_client(),
            limits=self._limits,
        )
        display = name or f"{owner}/{repo}"
        info = RepositoryInfo(
            id=repo_id,
            name=display,
            kind=RepositoryKind.github,
            root=canonical_url(owner, repo),
            snapshot=adapter.get_snapshot(),
            registered_at=datetime.now(tz=timezone.utc),
            file_count_hint=adapter.file_count,
        )
        self._repos[repo_id] = adapter
        self._info[repo_id] = info
        return info

    def get(self, repo_id: str) -> RepositoryInterface:
        try:
            return self._repos[repo_id]
        except KeyError:
            raise RepositoryNotFoundError(f"No repository registered with id '{repo_id}'.") from None

    def get_info(self, repo_id: str) -> RepositoryInfo:
        try:
            return self._info[repo_id]
        except KeyError:
            raise RepositoryNotFoundError(f"No repository registered with id '{repo_id}'.") from None

    def list(self) -> list[RepositoryInfo]:
        return list(self._info.values())
