"""Repository registration and listing."""

from __future__ import annotations

from fastapi import APIRouter

from code_intelligence.models import RepositoryInfo

from ..deps import get_registry
from ..schemas import RegisterRepoRequest

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryInfo, status_code=201)
def register_repository(body: RegisterRepoRequest) -> RepositoryInfo:
    """Register a repository by local path **or** GitHub URL. The source is
    auto-detected and routed to the matching adapter. Idempotent: the same local
    path — or the same GitHub ``owner/repo`` — returns the same repository id."""
    return get_registry().register(body.path, name=body.name)


@router.get("", response_model=list[RepositoryInfo])
def list_repositories() -> list[RepositoryInfo]:
    return get_registry().list()


@router.get("/{repo_id}", response_model=RepositoryInfo)
def get_repository(repo_id: str) -> RepositoryInfo:
    # get_info raises RepositoryNotFoundError (HTTP 404) for an unknown id.
    return get_registry().get_info(repo_id)


@router.delete("/{repo_id}", status_code=204)
def remove_repository(repo_id: str) -> None:
    """Unregister a repository from this application's in-memory registry.

    This only forgets the repository here — it never deletes files, the local
    directory, or anything on GitHub, and issues no git/MCP call. ``remove``
    raises RepositoryNotFoundError (HTTP 404) for an unknown id.
    """
    get_registry().remove(repo_id)
