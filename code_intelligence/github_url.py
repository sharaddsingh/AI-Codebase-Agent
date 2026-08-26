"""GitHub reference detection and parsing.

Two jobs:

* :func:`looks_like_github` — decide whether a user-supplied string is a GitHub
  reference (so the registry routes it to the GitHub adapter) or a local path.
  Detection inspects the *host* of the parsed URL, never a substring test like
  ``"github.com" in text`` — otherwise a local path such as
  ``/home/me/github.com-notes`` would be misrouted.

* :func:`parse_github_url` — turn a GitHub reference into a canonical
  ``(owner, repo)`` pair, raising :class:`InvalidGitHubUrlError` with a specific,
  user-facing message for anything malformed.

Supported forms (all resolve to ``owner`` / ``repo``)::

    https://github.com/owner/repo
    http://github.com/owner/repo
    https://www.github.com/owner/repo
    https://github.com/owner/repo.git
    https://github.com/owner/repo/          (trailing slash)
    github.com/owner/repo                    (scheme-less)
    git@github.com:owner/repo.git            (SSH)

A deep link to something *inside* a repo (``.../blob/main/x.py``,
``.../tree/dev``) is detected as GitHub but rejected by the parser with a message
telling the caller to pass the repository root instead.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .errors import InvalidGitHubUrlError

# Hosts we recognize as GitHub. (GitHub Enterprise on a custom host is out of
# scope for this pass; only github.com public/SaaS is supported.)
_GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})

# owner / repo segment charset accepted by GitHub: letters, digits, '-', '_', '.'
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# git@host:owner/repo(.git) — capture host and the "owner/repo" remainder.
_SSH_RE = re.compile(r"^git@(?P<host>[A-Za-z0-9.\-]+):(?P<path>.+)$")


def _split_host_path(text: str) -> tuple[str | None, list[str]]:
    """Return ``(host_lower_or_None, [path segments])`` for a URL-shaped string.

    Returns ``(None, [])`` for anything that is not URL-shaped (e.g. a local
    filesystem path), so the caller treats it as *not* GitHub. This never raises.
    """

    t = (text or "").strip()
    if not t:
        return None, []

    # SSH: git@github.com:owner/repo.git
    m = _SSH_RE.match(t)
    if m:
        host = m.group("host").lower()
        raw_path = m.group("path")
    elif "://" in t:
        parsed = urlparse(t)
        host = (parsed.hostname or "").lower()
        raw_path = parsed.path
    else:
        # Scheme-less: only URL-shaped if the first '/'-segment looks like a
        # hostname (contains a dot and no backslash). This keeps relative local
        # paths like "src/app" or Windows "C:\proj" out of the GitHub branch.
        unified = t.replace("\\", "/")
        first = unified.split("/", 1)[0]
        if "." not in first or "\\" in t.split("/", 1)[0]:
            return None, []
        parsed = urlparse("https://" + unified)
        host = (parsed.hostname or "").lower()
        raw_path = parsed.path

    segments = [s for s in raw_path.replace("\\", "/").split("/") if s]
    return (host or None), segments


def looks_like_github(text: str) -> bool:
    """True if ``text`` is a GitHub reference and should route to the GitHub adapter.

    Returns True for any github.com URL — including deep links and malformed
    owner/repo — so the registry hands it to the GitHub path, where
    :func:`parse_github_url` produces a *specific* error rather than the string
    silently falling through to a "path does not exist" local failure.
    """

    host, _ = _split_host_path(text)
    return host in _GITHUB_HOSTS


def parse_github_url(text: str) -> tuple[str, str]:
    """Parse a GitHub reference into ``(owner, repo)``.

    Raises :class:`InvalidGitHubUrlError` for non-GitHub hosts, missing
    owner/repo, deep links inside a repo, or illegal owner/repo characters.
    """

    host, segments = _split_host_path(text)
    if host not in _GITHUB_HOSTS:
        raise InvalidGitHubUrlError(
            "Not a GitHub repository URL. Expected https://github.com/<owner>/<repo>."
        )
    if len(segments) < 2:
        raise InvalidGitHubUrlError(
            "A GitHub URL must include both an owner and a repository, "
            "e.g. https://github.com/owner/repo."
        )
    if len(segments) > 2:
        raise InvalidGitHubUrlError(
            "Please provide the repository root URL (https://github.com/owner/repo), "
            "not a link to a file, branch, or subpath inside it."
        )

    owner, repo = segments[0], segments[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]

    if not repo or not _NAME_RE.match(owner) or not _NAME_RE.match(repo):
        raise InvalidGitHubUrlError(
            "The GitHub owner or repository name contains invalid characters."
        )
    return owner, repo


def canonical_url(owner: str, repo: str) -> str:
    """The canonical https URL for a repository (used as its display ``root``)."""

    return f"https://github.com/{owner}/{repo}"
