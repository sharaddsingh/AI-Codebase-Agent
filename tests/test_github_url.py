"""GitHub URL detection and parsing, plus registry source detection.

Pure-string logic — no network, no filesystem. Verifies every supported URL
form parses to ``(owner, repo)``, that malformed/deep/non-GitHub inputs raise a
specific :class:`InvalidGitHubUrlError`, and that :meth:`detect_source` routes
local paths and GitHub URLs correctly (the bug that started this work was a
GitHub URL being treated as a local path).
"""

from __future__ import annotations

import pytest

from code_intelligence.errors import InvalidGitHubUrlError
from code_intelligence.github_url import canonical_url, looks_like_github, parse_github_url
from code_intelligence.models import RepositoryKind
from code_intelligence.registry import RepositoryRegistry


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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("C:\\Users\\me\\project", RepositoryKind.local),
        ("C:/Users/me/project", RepositoryKind.local),
        ("/home/me/project", RepositoryKind.local),
        ("./relative/path", RepositoryKind.local),
        ("src/app", RepositoryKind.local),
        ("tests/fixtures/sample_repo", RepositoryKind.local),
        ("/home/me/github.com-notes", RepositoryKind.local),  # substring, not host
        ("https://github.com/owner/repo", RepositoryKind.github),
        ("github.com/owner/repo", RepositoryKind.github),
        ("git@github.com:owner/repo.git", RepositoryKind.github),
    ],
)
def test_detect_source_matrix(source: str, expected: RepositoryKind) -> None:
    assert RepositoryRegistry().detect_source(source) is expected
