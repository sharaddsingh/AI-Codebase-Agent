"""In-memory registry of authorized repositories.

For the MVP the registry lives in the backend process (no database).  It is the
single place that decides whether a path may be registered at all — optionally
constrained to a configured allow-list of roots — and it hands out
:class:`RepositoryInterface` instances by id to the rest of the system.

Registration is idempotent: registering the same real path twice returns the
same repository id (and refreshes its snapshot).

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
from .limits import DEFAULT_LIMITS, EngineLimits
from .local_adapter import LocalRepositoryAdapter
from .models import RepositoryInfo, RepositoryKind
from .paths import is_within
from .repository import RepositoryInterface


def _repo_id_for(real_path: str) -> str:
    return "repo_" + hashlib.sha256(os.path.normcase(real_path).encode("utf-8")).hexdigest()[:10]


class RepositoryRegistry:
    def __init__(
        self,
        *,
        allowed_roots: Sequence[str | Path] | None = None,
        respect_gitignore: bool = True,
        limits: EngineLimits = DEFAULT_LIMITS,
    ) -> None:
        self._repos: dict[str, RepositoryInterface] = {}
        self._info: dict[str, RepositoryInfo] = {}
        self._respect_gitignore = respect_gitignore
        self._limits = limits
        self._allowed_roots: list[str] = [
            os.path.realpath(str(p)) for p in (allowed_roots or [])
        ]

    @property
    def allowed_roots(self) -> list[str]:
        return list(self._allowed_roots)

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
