"""Repository registration and listing."""

from __future__ import annotations

from fastapi import APIRouter

from code_intelligence.models import RepositoryInfo

from ..deps import get_registry
from ..schemas import RegisterRepoRequest

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryInfo, status_code=201)
def register_repository(body: RegisterRepoRequest) -> RepositoryInfo:
    """Register a local repository by explicit path. Idempotent: registering the
    same real path returns the same repository id."""
    return get_registry().register_local(body.path, name=body.name)


@router.get("", response_model=list[RepositoryInfo])
def list_repositories() -> list[RepositoryInfo]:
    return get_registry().list()


@router.get("/{repo_id}", response_model=RepositoryInfo)
def get_repository(repo_id: str) -> RepositoryInfo:
    # get_info raises RepositoryNotFoundError (HTTP 404) for an unknown id.
    return get_registry().get_info(repo_id)
