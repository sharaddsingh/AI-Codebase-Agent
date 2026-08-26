"""RepositoryRegistry: registration, idempotency, and the allow-list guard."""

from __future__ import annotations

from pathlib import Path

import pytest
from github_mock import mock_client

from code_intelligence.errors import RegistrationError, RepositoryNotFoundError
from code_intelligence.models import RepositoryKind
from code_intelligence.registry import RepositoryRegistry

GH_URL = "https://github.com/octocat/hello"


def test_register_and_lookup(registry: RepositoryRegistry, sample_repo_path: Path) -> None:
    info = registry.register_local(str(sample_repo_path), name="sample")
    assert info.id.startswith("repo_")
    assert info.name == "sample"
    assert registry.get(info.id).id == info.id
    assert registry.get_info(info.id).name == "sample"
    assert len(registry.list()) == 1


def test_registration_is_idempotent(registry: RepositoryRegistry, sample_repo_path: Path) -> None:
    a = registry.register_local(str(sample_repo_path))
    b = registry.register_local(str(sample_repo_path))
    assert a.id == b.id
    assert len(registry.list()) == 1  # not duplicated


def test_unknown_id_raises(registry: RepositoryRegistry) -> None:
    with pytest.raises(RepositoryNotFoundError):
        registry.get("repo_does_not_exist")
    with pytest.raises(RepositoryNotFoundError):
        registry.get_info("repo_does_not_exist")


def test_missing_path_rejected(registry: RepositoryRegistry, tmp_path: Path) -> None:
    with pytest.raises(RegistrationError):
        registry.register_local(str(tmp_path / "nope"))


def test_empty_path_rejected(registry: RepositoryRegistry) -> None:
    with pytest.raises(RegistrationError):
        registry.register_local("   ")


def test_file_path_rejected(registry: RepositoryRegistry, sample_repo_path: Path) -> None:
    with pytest.raises(RegistrationError):
        registry.register_local(str(sample_repo_path / "README.md"))


def test_allowed_roots_block_outside(tmp_path: Path, sample_repo_path: Path) -> None:
    reg = RepositoryRegistry(allowed_roots=[tmp_path])
    with pytest.raises(RegistrationError):
        reg.register_local(str(sample_repo_path))


def test_allowed_roots_permit_within(tmp_path: Path) -> None:
    sub = tmp_path / "proj"
    sub.mkdir()
    reg = RepositoryRegistry(allowed_roots=[tmp_path])
    info = reg.register_local(str(sub))
    assert info.id.startswith("repo_")


# ---- GitHub registration (mocked network) ----------------------------------
def test_register_github_via_unified_entry() -> None:
    reg = RepositoryRegistry(github_client=mock_client())
    info = reg.register(GH_URL)  # auto-detected as GitHub, not a local path
    assert info.kind is RepositoryKind.github
    assert info.root == "https://github.com/octocat/hello"
    assert info.snapshot.id.startswith("gh:")
    assert reg.get(info.id).kind is RepositoryKind.github


def test_local_and_github_coexist(sample_repo_path: Path) -> None:
    reg = RepositoryRegistry(github_client=mock_client())
    local = reg.register(str(sample_repo_path))
    gh = reg.register(GH_URL)
    assert local.kind is RepositoryKind.local
    assert gh.kind is RepositoryKind.github
    assert local.id != gh.id
    kinds = {i.id: i.kind for i in reg.list()}
    assert kinds == {local.id: RepositoryKind.local, gh.id: RepositoryKind.github}


def test_github_registration_is_idempotent() -> None:
    reg = RepositoryRegistry(github_client=mock_client())
    a = reg.register(GH_URL)
    b = reg.register(GH_URL)
    assert a.id == b.id
    assert len(reg.list()) == 1  # not duplicated


def test_register_empty_source_rejected() -> None:
    with pytest.raises(RegistrationError):
        RepositoryRegistry().register("   ")
