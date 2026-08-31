"""Persistence for GitHub repository registrations.

Mirrors :mod:\`backend.uploaded_repos\` for the \`kind == "github"\` row of the
in-memory registry. The registry itself is process-local, but a backend
restart (a code edit under \`--reload\`, a redeploy, an orphan-worker swap)
would otherwise wipe every GitHub registration while the frontend keeps
holding the same \`repo_<sha>\` id, producing a wedged UI: every subsequent
DELETE / file-tree call returns "No repository registered with id ...".

We persist the canonical GitHub URL (\`info.root\` on GitHub rows) and the
optional display name in a single JSON file under the upload root's existing
\`.meta/\` sidecar directory. URLs are the unique key, so re-registering the
same URL is idempotent.

Security / containment properties:
* Only the URL and display name are written - never the token, the response
  body, or any MCP-side state.
* Writes are atomic (write \`.tmp\` then rename) so a crash mid-write cannot
  leave a half-formed file that the next read would reject.
* A corrupted file is logged and treated as empty; we never block startup
  on bad on-disk state.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("backend.github_state")

# Same sidecar directory uploaded_repos.py uses for per-repo display names.
# Putting the GitHub state here keeps every "remember-me" artifact in one
# place and one naming convention.
_STATE_FILENAME = "github_repos.json"


@dataclass(frozen=True)
class StoredGitHubRepo:
    url: str
    name: str | None


def _state_path(upload_root: Path) -> Path:
    return Path(upload_root) / ".meta" / _STATE_FILENAME


def _read_raw(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        log.warning("could not read github repo state at %s: %s", path, exc)
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        log.warning("github repo state at %s is malformed; treating as empty", path)
        return []
    if not isinstance(parsed, list):
        log.warning("github repo state at %s is not a list; treating as empty", path)
        return []
    return [e for e in parsed if isinstance(e, dict)]


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # NamedTemporaryFile on the same directory guarantees the rename is
    # atomic on Windows + POSIX (same volume / filesystem).
    fd, tmp_name = tempfile.mkstemp(
        prefix=".github_repos.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup of the temp file if rename never happened.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def discover_github_repos(upload_root: Path) -> list[StoredGitHubRepo]:
    """Read every persisted GitHub registration. Returns an empty list when
    the state file is missing, unreadable, or malformed - never raises."""

    out: list[StoredGitHubRepo] = []
    seen: set[str] = set()
    for entry in _read_raw(_state_path(Path(upload_root))):
        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        # Deduplicate by URL so a half-written file or a double-recorded
        # entry doesn't produce two registry rows for the same repo.
        key = url.strip()
        if key in seen:
            continue
        seen.add(key)
        name = entry.get("name")
        out.append(StoredGitHubRepo(url=key, name=name if isinstance(name, str) else None))
    return out


def record_github_repo(upload_root: Path, *, url: str, name: str | None) -> None:
    """Add or replace an entry. Idempotent on URL - re-recording the same URL
    just updates the stored display name."""

    url = url.strip()
    if not url:
        return
    path = _state_path(Path(upload_root))
    entries = _read_raw(path)
    new_entry = {"url": url, "name": name if isinstance(name, str) else None}
    replaced = False
    for i, entry in enumerate(entries):
        if isinstance(entry.get("url"), str) and entry["url"].strip() == url:
            entries[i] = new_entry
            replaced = True
            break
    if not replaced:
        entries.append(new_entry)
    payload = json.dumps(entries, indent=2, ensure_ascii=False)
    _atomic_write(path, payload)


def forget_github_repo(upload_root: Path, *, url: str) -> bool:
    """Remove an entry by URL. Returns True if anything was removed, False if
    the URL was not in the state file. Never raises for "not present"."""

    url = url.strip()
    if not url:
        return False
    path = _state_path(Path(upload_root))
    entries = _read_raw(path)
    kept = [
        e
        for e in entries
        if not (isinstance(e.get("url"), str) and e["url"].strip() == url)
    ]
    if len(kept) == len(entries):
        return False
    payload = json.dumps(kept, indent=2, ensure_ascii=False)
    _atomic_write(path, payload)
    return True
