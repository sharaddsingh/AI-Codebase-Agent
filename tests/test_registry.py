"""RepositoryRegistry: registration, idempotency, and removal.

The registry has two public registration paths — :meth:`register_uploaded`
(browser upload pipeline) and :meth:`register_github` (MCP). There is no
``register_local``: a user-supplied filesystem path is never accepted.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from github_mock import mock_client

from code_intelligence.errors import RegistrationError, RepositoryNotFoundError
from code_intelligence.models import RepositoryKind
from code_intelligence.registry import RepositoryRegistry

GH_URL = "https://github.com/octocat/hello"


def test_register_uploaded_and_lookup(
    registry: RepositoryRegistry, sample_repo_path: Path, tmp_path: Path
) -> None:
    # Copy the fixture into the upload root so the registry is registering a
    # real on-disk tree it owns.
    uploaded = tmp_path / "up_aaaaaaaaaaaa"
    shutil.copytree(sample_repo_path, uploaded)
    info = registry.register_uploaded(uploaded, name="sample")
    assert info.id.startswith("up_")
    assert info.kind is RepositoryKind.local
    assert registry.get(info.id).id == info.id
    assert registry.get_info(info.id).name == "sample"
    assert len(registry.list()) == 1


def test_uploaded_registration_is_idempotent(
    registry: RepositoryRegistry, sample_repo_path: Path, tmp_path: Path
) -> None:
    uploaded = tmp_path / "up_bbbbbbbbbbbb"
    shutil.copytree(sample_repo_path, uploaded)
    a = registry.register_uploaded(uploaded)
    b = registry.register_uploaded(uploaded)
    assert a.id == b.id
    assert len(registry.list()) == 1


def test_register_uploaded_rejects_missing_dir(
    registry: RepositoryRegistry, tmp_path: Path
) -> None:
    with pytest.raises(RegistrationError):
        registry.register_uploaded(tmp_path / "never-existed")


def test_register_uploaded_rejects_file(
    registry: RepositoryRegistry, sample_repo_path: Path
) -> None:
    with pytest.raises(RegistrationError):
        registry.register_uploaded(sample_repo_path / "README.md")


# ---- GitHub registration (mocked network) ----------------------------------
def test_register_github() -> None:
    reg = RepositoryRegistry(github_mcp_client=mock_client())
    info = reg.register_github(GH_URL)
    assert info.kind is RepositoryKind.github
    assert info.root == "https://github.com/octocat/hello"
    assert info.snapshot.id.startswith("gh:")
    assert reg.get(info.id).kind is RepositoryKind.github


def test_github_registration_is_idempotent() -> None:
    reg = RepositoryRegistry(github_mcp_client=mock_client())
    a = reg.register_github(GH_URL)
    b = reg.register_github(GH_URL)
    assert a.id == b.id
    assert len(reg.list()) == 1


def test_local_and_github_coexist(
    registry: RepositoryRegistry, sample_repo_path: Path, tmp_path: Path
) -> None:
    reg = RepositoryRegistry(github_mcp_client=mock_client())
    uploaded = tmp_path / "up_cccccccccccc"
    shutil.copytree(sample_repo_path, uploaded)
    local = reg.register_uploaded(uploaded)
    gh = reg.register_github(GH_URL)
    assert local.kind is RepositoryKind.local
    assert gh.kind is RepositoryKind.github
    assert local.id != gh.id
    kinds = {i.id: i.kind for i in reg.list()}
    assert kinds == {local.id: RepositoryKind.local, gh.id: RepositoryKind.github}


# ---- Removal (forget from the in-memory registry only) ---------------------
def test_remove_forgets_repository(
    registry: RepositoryRegistry, sample_repo_path: Path, tmp_path: Path
) -> None:
    uploaded = tmp_path / "up_dddddddddddd"
    shutil.copytree(sample_repo_path, uploaded)
    info = registry.register_uploaded(uploaded)
    assert len(registry.list()) == 1
    registry.remove(info.id)
    assert registry.list() == []
    with pytest.raises(RepositoryNotFoundError):
        registry.get(info.id)
    with pytest.raises(RepositoryNotFoundError):
        registry.get_info(info.id)


def test_remove_unknown_id_raises(registry: RepositoryRegistry) -> None:
    with pytest.raises(RepositoryNotFoundError):
        registry.remove("repo_does_not_exist")


def test_remove_one_leaves_others(
    registry: RepositoryRegistry, sample_repo_path: Path, tmp_path: Path
) -> None:
    a_dir = tmp_path / "up_eeeeeeeeeeee"
    b_dir = tmp_path / "up_ffffffffffff"
    shutil.copytree(sample_repo_path, a_dir)
    shutil.copytree(sample_repo_path, b_dir)
    a = registry.register_uploaded(a_dir)
    b = registry.register_uploaded(b_dir)
    registry.remove(a.id)
    assert [i.id for i in registry.list()] == [b.id]
    assert registry.get(b.id).id == b.id


def test_remove_does_not_delete_filesystem(
    registry: RepositoryRegistry, sample_repo_path: Path, tmp_path: Path
) -> None:
    # The on-disk upload directory must survive a registry-only removal.
    uploaded = tmp_path / "up_111111111111"
    shutil.copytree(sample_repo_path, uploaded)
    info = registry.register_uploaded(uploaded)
    registry.remove(info.id)
    assert uploaded.is_dir()
    assert (uploaded / "README.md").exists()


def test_remove_github_repo() -> None:
    reg = RepositoryRegistry(github_mcp_client=mock_client())
    gh = reg.register_github(GH_URL)
    reg.remove(gh.id)
    assert reg.list() == []
    again = reg.register_github(GH_URL)
    assert again.kind is RepositoryKind.github
