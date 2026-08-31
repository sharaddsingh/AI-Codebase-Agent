"""GitHub URL detection and parsing.

Pure-string logic — no network, no filesystem. Verifies every supported URL
form parses to ``(owner, repo)``, and that malformed/deep/non-GitHub inputs
raise a specific :class:`InvalidGitHubUrlError`.

The registry used to auto-detect local-path-vs-GitHub via
:meth:`RepositoryRegistry.detect_source` and route accordingly. The two are
now explicit API endpoints (``POST /api/repositories/upload`` and
``POST /api/repositories/github``), so source detection is gone and these
tests focus on the URL parsing the GitHub endpoint relies on.
"""

from __future__ import annotations

import pytest

from code_intelligence.errors import InvalidGitHubUrlError
from code_intelligence.github_url import canonical_url, looks_like_github, parse_github_url


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/octocat/Hello-World",
        "http://github.com/octocat/Hello-World",
        "https://www.github.com/octocat/Hello-World",
        "https://github.com/octocat/Hello-World.git",
        "https://github.com/octocat/Hello-World/",
        "github.com/octocat/Hello-World",
        "git@github.com:octocat/Hello-World.git",
    ],
)
def test_parse_supported_forms(text: str) -> None:
    assert looks_like_github(text) is True
    assert parse_github_url(text) == ("octocat", "Hello-World")


def test_canonical_url_is_stable() -> None:
    assert canonical_url("octocat", "Hello-World") == "https://github.com/octocat/Hello-World"


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/octocat",  # missing repo
        "https://github.com/",  # missing both
        "https://github.com/octocat/Hello-World/blob/main/app.py",  # deep: file
        "https://github.com/octocat/Hello-World/tree/dev",  # deep: branch
        "https://github.com/octocat/repo!",  # illegal repo char
    ],
)
def test_parse_rejects_github_but_unusable(text: str) -> None:
    # Detected as GitHub (host is github.com) so the registry hands it to the
    # GitHub path, where the parser produces a *specific* error instead of a
    # misleading "path does not exist".
    assert looks_like_github(text) is True
    with pytest.raises(InvalidGitHubUrlError):
        parse_github_url(text)


@pytest.mark.parametrize(
    "text",
    [
        "https://gitlab.com/octocat/repo",
        "https://notgithub.com/octocat/repo",
        "https://example.com/github.com/octocat/repo",  # github.com only in the path
        "",
    ],
)
def test_non_github_hosts_are_not_github(text: str) -> None:
    assert looks_like_github(text) is False
    with pytest.raises(InvalidGitHubUrlError):
        parse_github_url(text)
