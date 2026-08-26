"""Ignore rules for traversal and search.

Two layers, both on by default:

1. A built-in deny-list of noisy directories and generated files (``.git``,
   ``node_modules``, virtual envs, build output, lockfiles, minified bundles).
2. Optional ``.gitignore`` support at the repository root via :mod:`pathspec`.

Binary files and oversized files are handled by the engine at read time; this
module only decides what to *list* and *walk*.

Note (deferred): only the root ``.gitignore`` is honored in this MVP.  Nested
``.gitignore`` files and full git precedence rules are a later-phase refinement.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

try:  # pathspec is a listed dependency, but degrade gracefully if absent.
    import pathspec

    _HAS_PATHSPEC = True
except Exception:  # pragma: no cover - defensive
    pathspec = None  # type: ignore[assignment]
    _HAS_PATHSPEC = False


DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git", ".hg", ".svn",
        "node_modules", "bower_components",
        ".venv", "venv", "env", ".env.d", "virtualenv",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
        "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit",
        ".gradle", ".idea", ".vscode", ".cache", ".turbo", ".parcel-cache",
        "coverage", "htmlcov", ".terraform", "vendor", "Pods",
        ".DS_Store",
    }
)

DEFAULT_IGNORE_FILE_GLOBS: tuple[str, ...] = (
    "*.min.js",
    "*.min.css",
    "*.map",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.o",
    "*.a",
)


class IgnoreRules:
    """Decides whether a repository-relative path is ignored."""

    def __init__(
        self,
        ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS,
        file_globs: tuple[str, ...] = DEFAULT_IGNORE_FILE_GLOBS,
        gitignore_spec: pathspec.PathSpec | None = None,
    ) -> None:
        self.ignore_dirs = ignore_dirs
        self.file_globs = file_globs
        self._spec = gitignore_spec

    @classmethod
    def for_root(cls, root: Path, respect_gitignore: bool = True) -> IgnoreRules:
        spec = None
        if respect_gitignore and _HAS_PATHSPEC:
            gitignore = root / ".gitignore"
            if gitignore.is_file():
                try:
                    lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
                    spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
                except OSError:
                    spec = None
        return cls(gitignore_spec=spec)

    def is_ignored_dir_name(self, name: str) -> bool:
        return name in self.ignore_dirs

    def is_ignored(self, rel_posix: str, is_dir: bool) -> bool:
        """Return True if the given repo-relative POSIX path should be skipped."""

        if not rel_posix:
            return False

        parts = rel_posix.split("/")
        # Any ignored directory component anywhere in the path.
        for part in parts[:-1] if not is_dir else parts:
            if part in self.ignore_dirs:
                return True
        if is_dir and parts and parts[-1] in self.ignore_dirs:
            return True

        name = parts[-1]
        if not is_dir:
            for glob in self.file_globs:
                if fnmatch(name, glob):
                    return True

        if self._spec is not None:
            probe = rel_posix + "/" if is_dir else rel_posix
            if self._spec.match_file(probe):
                return True

        return False
