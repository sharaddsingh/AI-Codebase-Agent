"""RepositoryRegistry: registration, idempotency, and the allow-list guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_intelligence.errors import RegistrationError, RepositoryNotFoundError
from code_intelligence.registry import RepositoryRegistry


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
