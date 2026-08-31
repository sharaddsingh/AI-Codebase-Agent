"""Upload repositories to the backend from a browser.

When a user picks a folder (or drags one) onto the web UI, the browser walks the
folder and streams its files to ``POST /api/repositories/upload``. This module
owns the **filesystem half** of that pipeline: writing the files into a fresh
per-upload directory and wiping that directory when an uploaded repo is removed.
The **registry half** (building the ``LocalRepositoryAdapter`` and inserting it
into the in-memory registry) lives in
:meth:`code_intelligence.registry.RepositoryRegistry.register_uploaded`, called
by the router once the files are on disk.

Security / containment properties:

* Each uploaded repo lives under a per-repo directory named after its id, which
  is itself nested under the resolved ``upload_root`` (default
  ``./uploaded_repos/``).
* Every incoming relative path is run through :func:`paths.normalize_relative`
  and verified to live inside the per-repo root (no ``..``, no absolute, no
  NUL bytes, no symlink escapes — the latter is enforced by writing only files
  we just received, never following links that might already be on disk).
* Hard caps on total bytes, per-file bytes, and file count.  Exceeding any cap
  aborts the upload and removes the partial directory.
* Removing an uploaded repo also wipes its on-disk directory.  Removing a
  GitHub repo leaves the remote repository untouched (unchanged behaviour).

Surviving a restart: the registry is in-memory, but these directories are not,
so :func:`discover_uploaded_repos` lets the app re-register whatever a previous
process left behind (see :func:`backend.deps.rehydrate_uploads`). Display names
are the one thing not recoverable from the tree itself, so they are written to a
sidecar under ``upload_root/.meta/``  — deliberately *outside* the repo
directory, since anything inside it would show up in the file tree, in search
results, and in the agent's citations.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from starlette.datastructures import UploadFile

from code_intelligence.errors import (
    PathValidationError,
    RegistrationError,
)
from code_intelligence.ignore import IgnoreRules
from code_intelligence.paths import is_within, normalize_relative

log = logging.getLogger("backend.upload")

# Upper bound on the client-supplied display name. Long enough for any real
# folder name, short enough that it cannot bloat a response or the UI.
MAX_REPO_NAME_LEN = 80

# Every per-upload directory is named "<prefix><token>". The prefix is what
# lets :func:`discover_uploaded_repos` tell our directories apart from anything
# else sharing the upload root — notably the sidecar directory below.
UPLOAD_DIR_PREFIX = "up_"

# Display names are persisted *beside* the repo directories, never inside them:
# a file written into the repo itself would show up in the file tree, in search
# results, and in the agent's citations. The leading dot also keeps this
# directory out of the ``up_*`` scan.
UPLOAD_META_DIRNAME = ".meta"


def _meta_path(upload_root: Path, dir_name: str) -> Path:
    return Path(upload_root) / UPLOAD_META_DIRNAME / f"{dir_name}.json"


def write_upload_meta(upload_root: Path, repo_dir: Path, name: str) -> None:
    """Record an uploaded repo's display name so it survives a restart.

    Best-effort by design: losing the sidecar costs the repo its pretty name
    after a restart (it falls back to the directory name), which is not worth
    failing an otherwise-good upload over.
    """

    path = _meta_path(upload_root, Path(repo_dir).name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name}), encoding="utf-8")
    except OSError as exc:
        log.warning("could not record upload metadata for %s: %s", path.name, exc)


def read_upload_meta(upload_root: Path, repo_dir: Path) -> str | None:
    """Read back a display name written by :func:`write_upload_meta`.

    Returns ``None`` when there is no sidecar, it is unreadable or malformed,
    or nothing usable survives :func:`sanitize_repo_name` — in every case the
    caller falls back to the directory name. Re-sanitizing on the way in is the
    point: this is a file on disk, so it is treated as untrusted input even
    though we wrote it, and a hand-edited upload root cannot smuggle control
    characters into the UI.
    """

    path = _meta_path(upload_root, Path(repo_dir).name)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    return sanitize_repo_name(name) if isinstance(name, str) else None


def discover_uploaded_repos(upload_root: Path) -> list[tuple[Path, str | None]]:
    """Find upload directories a previous process left in ``upload_root``.

    Returns ``(directory, display_name_or_None)`` pairs, sorted by directory
    name so startup is deterministic. Only directories named like an upload id
    are returned, which skips the ``.meta`` sidecar directory and anything a
    user dropped into the upload root by hand.
    """

    root = Path(upload_root)
    if not root.is_dir():
        return []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        log.warning("could not scan upload root %s: %s", root, exc)
        return []

    found: list[tuple[Path, str | None]] = []
    for entry in entries:
        if not entry.name.startswith(UPLOAD_DIR_PREFIX):
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:  # pragma: no cover - unreadable entry
            continue
        found.append((entry, read_upload_meta(root, entry)))
    return found


def sanitize_repo_name(name: str | None) -> str | None:
    """Clean a client-supplied display name for an uploaded folder.

    This name is display-only — it never reaches the filesystem, because the
    on-disk directory is named from the content hash. We still reduce it to a
    single path segment and drop non-printable characters so it can't be
    mistaken for a path or smuggle control codes into logs and the UI, and we
    bound its length.

    Returns ``None`` when nothing usable is left, which makes the caller fall
    back to the directory name.
    """

    if name is None:
        return None
    # Browsers may hand us a whole relative path; keep only the last segment.
    segment = name.replace("\\", "/").rstrip("/").rpartition("/")[2]
    cleaned = "".join(ch for ch in segment if ch.isprintable()).strip()
    if not cleaned or cleaned in (".", ".."):
        return None
    return cleaned[:MAX_REPO_NAME_LEN]


@dataclass(frozen=True)
class UploadLimits:
    """Hard caps for a single upload.

    ``max_files`` is the cap people actually hit — a mid-sized project easily
    runs to five figures of files — so it is set high, and the memory cost of
    that is bounded by ``max_total_bytes`` rather than by the count. The
    defaults here mirror ``UPLOAD_MAX_*`` in :class:`backend.config.Settings`;
    override them there, per deployment, not by editing this class.

    ``max_total_bytes`` is deliberately the conservative one: the multipart
    parser buffers each part (in memory below 1 MB, spooled to a temp file
    above it) before :func:`save_upload` writes any of them, so this cap is
    what keeps a large upload from being a memory problem on a small host.
    """

    max_total_bytes: int = 100 * 1024 * 1024  # 100 MB total
    max_file_bytes: int = 10 * 1024 * 1024   # 10 MB per file
    max_files: int = 20_000


def _drain(upload: UploadFile) -> None:
    """Drain and close an UploadFile's body without writing it anywhere.

    Used when we deliberately skip a file (ignored dir, empty path) so the
    underlying stream is properly closed and the client doesn't see a broken
    pipe mid-upload.

    Every step is best-effort: the file is being discarded either way, so a
    failure to seek/read/close it must not abort an otherwise valid upload.
    """

    try:
        upload.file.seek(0)
    except Exception:  # noqa: S110 - best-effort drain
        pass
    try:
        upload.file.read()
    except Exception:  # noqa: S110 - best-effort drain
        pass
    finally:
        try:
            upload.file.close()
        except Exception:  # noqa: S110 - best-effort cleanup
            pass


def save_upload(
    upload_root: Path,
    files: Iterable[UploadFile],
    *,
    limits: UploadLimits,
) -> tuple[str, Path, list[str]]:
    """Persist the uploaded files under ``upload_root/<repo_id>/``.

    Returns ``(repo_id, root_dir, relative_paths_written)``.  On any failure
    the partial directory is removed before re-raising so a half-uploaded
    repo never leaks.
    """

    upload_root = Path(upload_root).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)

    # Use a fresh per-upload token so every upload gets its own directory.
    # Note this is NOT the registry id: the registry derives that by hashing the
    # resolved directory path (registry._repo_id_for), which is what makes
    # re-registering the same directory — on a later upload of the same folder,
    # or when rehydrating on startup — produce the same id every time.
    repo_id = f"{UPLOAD_DIR_PREFIX}{uuid.uuid4().hex[:12]}"
    repo_dir = upload_root / repo_id
    repo_dir.mkdir(parents=False, exist_ok=False)

    written: list[str] = []
    total_bytes = 0
    file_count = 0
    ignored_dirs = IgnoreRules().ignore_dirs
    try:
        for upload in files:
            rel_raw = upload.filename or ""
            if not rel_raw:
                _drain(upload)
                continue

            try:
                rel = normalize_relative(rel_raw)
            except PathValidationError as exc:
                _drain(upload)
                raise RegistrationError(
                    f"Uploaded path is unsafe ({rel_raw!r}): {exc.message}"
                ) from exc

            if not rel:
                _drain(upload)
                continue

            # Refuse anything that smells like an ignored top-level component.
            top = rel.split("/", 1)[0]
            if top in ignored_dirs:
                _drain(upload)
                continue

            # Resolve the target and verify containment.
            target = (repo_dir / rel).resolve()
            if not is_within(str(repo_dir), str(target)):
                _drain(upload)
                raise PathValidationError(
                    f"Uploaded path escapes the upload root: {rel!r}"
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            bytes_written = 0
            try:
                with open(target, "wb") as fh:
                    while True:
                        chunk = upload.file.read(64 * 1024)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if bytes_written > limits.max_file_bytes:
                            raise RegistrationError(
                                f"File {rel!r} exceeds the {limits.max_file_bytes // 1024} KB per-file limit."
                            )
                        total_bytes += len(chunk)
                        if total_bytes > limits.max_total_bytes:
                            raise RegistrationError(
                                f"Upload exceeds the {limits.max_total_bytes // (1024 * 1024)} MB total limit."
                            )
                        fh.write(chunk)
            except OSError as exc:
                raise RegistrationError(
                    f"Could not write {rel!r}: {exc.strerror or exc}"
                ) from exc
            finally:
                try:
                    upload.file.close()
                except Exception:  # noqa: S110 - best-effort cleanup
                    pass

            file_count += 1
            if file_count > limits.max_files:
                raise RegistrationError(
                    f"Upload exceeds the {limits.max_files}-file limit."
                )
            written.append(rel)
    except Exception:
        # Best-effort cleanup of partial state.
        shutil.rmtree(repo_dir, ignore_errors=True)
        raise

    if not written:
        shutil.rmtree(repo_dir, ignore_errors=True)
        raise RegistrationError("Upload contained no files.")

    return repo_id, repo_dir, written


def cleanup_uploaded_repo(root: str) -> bool:
    """Remove the on-disk directory of an uploaded repo, and its name sidecar.

    Returns True if anything was removed, False if the path was not present.
    Never raises for "not present". The sidecar has to go too, or a removed
    repo's name would linger in the upload root forever.
    """

    if not root:
        return False
    try:
        target = Path(root).resolve()
    except OSError:
        return False

    parent = target.parent
    try:
        if not parent.exists() or not target.exists():
            return False
        if target == parent:  # refuse to remove the upload root itself
            return False
        shutil.rmtree(target, ignore_errors=True)
        _meta_path(parent, target.name).unlink(missing_ok=True)
        return True
    except OSError as exc:
        log.warning("could not remove uploaded repo %s: %s", root, exc)
        return False


def is_uploaded_repo_path(root: str, upload_root: str) -> bool:
    """True iff ``root`` lives under the configured ``upload_root``.

    Used by the DELETE handler to decide whether removing a repo also needs to
    wipe its on-disk directory. Both arguments are realpath'd before comparing
    so symlinks and case-sensitivity don't surprise us.
    """

    try:
        upload_real = os.path.realpath(upload_root)
        root_real = os.path.realpath(root)
    except OSError:
        return False
    if root_real == upload_real:
        return True
    return root_real.startswith(upload_real + os.sep)
