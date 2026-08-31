"""In-memory registry of authorized repositories.

The registry is the single place that decides *what* may be registered and
*how*: each kind (browser upload, GitHub) has its own :meth:`register_<kind>`
method so the API layer can pick the right one explicitly. Local repositories
never come from a user-supplied filesystem path — they always arrive via the
upload flow (:mod:`backend.uploaded_repos`) which already enforced the
containment, ignore-dir, and size guards before persisting anything. GitHub
repositories never touch disk; they are read over the official GitHub MCP
server using a server-side PAT.

Registration is idempotent: re-registering the same uploaded directory — or
the same ``owner/repo`` — returns the same repository id (and refreshes its
snapshot).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .engine import count_files
from .errors import RegistrationError, RepositoryNotFoundError
from .github_mcp_client import GitHubMCPClient, RemoteHttpTransport
from .github_mcp_repository import GitHubMCPRepository
from .github_url import canonical_url, parse_github_url
from .limits import DEFAULT_LIMITS, EngineLimits
from .local_adapter import LocalRepositoryAdapter
from .models import RepositoryInfo, RepositoryKind
from .repository import RepositoryInterface


def _repo_id_for(real_path: str) -> str:
    return "up_" + hashlib.sha256(real_path.encode("utf-8")).hexdigest()[:12]


def _repo_id_for_github(owner: str, repo: str) -> str:
    # Case-insensitive on owner/repo so re-registering the same repo with
    # different casing is idempotent (GitHub names are case-insensitive).
    key = f"github:{owner.lower()}/{repo.lower()}"
    return "repo_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


class RepositoryRegistry:
    def __init__(
        self,
        *,
        limits: EngineLimits = DEFAULT_LIMITS,
        github_token: str | None = None,
        github_mcp_url: str = "https://api.githubcopilot.com/mcp/readonly",
        github_mcp_toolsets: str = "repos,git",
        github_mcp_timeout: float = 30.0,
        github_mcp_client: GitHubMCPClient | None = None,
    ) -> None:
        self._repos: dict[str, RepositoryInterface] = {}
        self._info: dict[str, RepositoryInfo] = {}
        self._limits = limits
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

    def register_uploaded(self, repo_dir: Path, name: str | None = None) -> RepositoryInfo:
        """Register a directory that the upload flow has already written to disk.

        The path must be one we just wrote — there is no allow-list or path
        validation here, because the only thing allowed to land in the upload
        root is the upload pipeline itself. The adapter ignores
        ``node_modules``/``.git``/etc. and enforces the engine size limits.
        """

        repo_dir = Path(repo_dir).resolve()
        if not repo_dir.exists():
            raise RegistrationError(f"Upload directory does not exist: {repo_dir}")
        if not repo_dir.is_dir():
            raise RegistrationError(f"Upload path is not a directory: {repo_dir}")

        repo_id = _repo_id_for(str(repo_dir))
        display = name or repo_dir.name or repo_id

        adapter = LocalRepositoryAdapter(
            repo_id,
            display,
            repo_dir,
            limits=self._limits,
        )
        info = RepositoryInfo(
            id=repo_id,
            name=display,
            kind=RepositoryKind.local,
            root=str(repo_dir),
            snapshot=adapter.get_snapshot(),
            registered_at=datetime.now(tz=timezone.utc),
            file_count_hint=count_files(repo_dir, adapter.ignore, limits=self._limits),
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
        not-found / tool error), never a raw response or the token.
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

    def remove(self, repo_id: str) -> None:
        """Forget a repository — remove it from the in-memory registry only.

        This drops both internal maps for ``repo_id`` and releases the adapter
        reference. It performs **no** filesystem, git, or GitHub/MCP operation:
        the upload directory and the remote GitHub repository are left
        completely untouched by this call (the upload router is responsible
        for any on-disk cleanup of an uploaded directory). The shared GitHub
        MCP session is intentionally *not* closed here — other GitHub repos
        may still be using it, and it is closed only on app shutdown via
        :meth:`close_github_mcp`. Raises :class:`RepositoryNotFoundError` for
        an unknown id (mirrors :meth:`get`/:meth:`get_info`).
        """

        if repo_id not in self._info:
            raise RepositoryNotFoundError(f"No repository registered with id '{repo_id}'.")
        self._repos.pop(repo_id, None)
        del self._info[repo_id]
