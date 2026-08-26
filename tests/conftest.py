"""Shared pytest fixtures.

The sample repository under ``tests/fixtures/sample_repo`` is a small but
realistic FastAPI-style app used by nearly every test. It deliberately contains
things the engine must handle: ignored dirs (``node_modules``), a binary file
(``assets/logo.bin``), and a prompt-injection fixture (``app/notes.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_intelligence.local_adapter import LocalRepositoryAdapter
from code_intelligence.registry import RepositoryRegistry

FIXTURE_REPO = (Path(__file__).parent / "fixtures" / "sample_repo").resolve()


@pytest.fixture(scope="session")
def sample_repo_path() -> Path:
    assert FIXTURE_REPO.is_dir(), f"missing fixture repo: {FIXTURE_REPO}"
    return FIXTURE_REPO


@pytest.fixture
def repo(sample_repo_path: Path) -> LocalRepositoryAdapter:
    return LocalRepositoryAdapter("repo_test", "sample", sample_repo_path)


@pytest.fixture
def registry() -> RepositoryRegistry:
    return RepositoryRegistry()
