"""Local filesystem implementation of :class:`RepositoryInterface`.

Every method delegates to the bounded, containment-checked functions in
:mod:`code_intelligence.engine` / :mod:`retrieval.lexical`.  All access is
confined to the authorized ``root`` captured at construction.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .engine import (
    build_directory_listing,
    get_metadata,
    read_text_file,
)
from .errors import RegistrationError
from .ignore import IgnoreRules
from .limits import DEFAULT_LIMITS, EngineLimits
from .models import (
    DirectoryListing,
    FileContent,
    FileMetadata,
    RepositoryKind,
    RepoSnapshot,
    SearchResults,
)
from .repository import RepositoryInterface


class LocalRepositoryAdapter(RepositoryInterface):
    kind = RepositoryKind.local

    def __init__(
        self,
        repo_id: str,
        name: str,
        root: str | Path,
        *,
        respect_gitignore: bool = True,
        limits: EngineLimits = DEFAULT_LIMITS,
    ) -> None:
        real = Path(os.path.realpath(str(root)))
        if not real.exists():
            raise RegistrationError(f"Repository path does not exist: {root}")
        if not real.is_dir():
            raise RegistrationError(f"Repository path is not a directory: {root}")
        self.id = repo_id
        self.display_name = name
        self._root = real
        self._limits = limits
        self._ignore = IgnoreRules.for_root(real, respect_gitignore=respect_gitignore)
        self._snapshot = self._capture_snapshot()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def ignore(self) -> IgnoreRules:
        return self._ignore

    # ---- snapshot -------------------------------------------------------
    def _capture_snapshot(self) -> RepoSnapshot:
        now = datetime.now(tz=timezone.utc)
        git_dir = self._root / ".git"
        if git_dir.exists() and shutil.which("git"):
            try:
                rev = subprocess.run(  # noqa: S603
                    ["git", "-C", str(self._root), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if rev.returncode == 0 and rev.stdout.strip():
                    revision = rev.stdout.strip()
                    status = subprocess.run(  # noqa: S603
                        ["git", "-C", str(self._root), "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    dirty = bool(status.stdout.strip())
                    sid = f"git:{revision[:12]}" + ("+dirty" if dirty else "")
                    return RepoSnapshot(
                        id=sid,
                        kind="git",
                        revision=revision,
                        dirty=dirty,
                        captured_at=now,
                    )
            except (OSError, subprocess.SubprocessError):
                pass
        # Non-git working tree: stable id derived from the root path.
        digest = hashlib.sha256(str(self._root).encode("utf-8")).hexdigest()[:12]
        return RepoSnapshot(id=f"wt:{digest}", kind="working-tree", captured_at=now)

    def get_snapshot(self) -> RepoSnapshot:
        return self._snapshot

    def refresh_snapshot(self) -> RepoSnapshot:
        self._snapshot = self._capture_snapshot()
        return self._snapshot

    # ---- capabilities ---------------------------------------------------
    def list_files(
        self, path: str = "", *, page: int = 1, page_size: int | None = None
    ) -> DirectoryListing:
        return build_directory_listing(
            self._root,
            self.id,
            path,
            page=page,
            page_size=page_size,
            ignore=self._ignore,
            limits=self._limits,
        )

    def read_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        max_bytes: int | None = None,
    ) -> FileContent:
        return read_text_file(
            self._root,
            self.id,
            path,
            start_line=start_line,
            end_line=end_line,
            max_bytes=max_bytes,
            limits=self._limits,
        )

    def get_file_metadata(self, path: str) -> FileMetadata:
        return get_metadata(self._root, self.id, path, limits=self._limits)

    def search_code(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        path_glob: str | None = None,
        max_results: int | None = None,
    ) -> SearchResults:
        # Imported lazily to keep the retrieval → code_intelligence dependency
        # one-directional (avoids an import cycle at package load time).
        from retrieval.lexical import search

        return search(
            self._root,
            self._ignore,
            query,
            regex=regex,
            case_sensitive=case_sensitive,
            path_glob=path_glob,
            max_results=max_results,
            limits=self._limits,
            repo_id=self.id,
        )
