"""File-tree, file-content, and file-metadata endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from code_intelligence.models import DirectoryListing, FileContent, FileMetadata

from ..deps import get_repo_or_404

router = APIRouter(prefix="/repositories/{repo_id}", tags=["files"])


@router.get("/tree", response_model=DirectoryListing)
def get_tree(
    repo_id: str,
    path: str = Query("", description="Repo-relative directory path; '' for root."),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1),
) -> DirectoryListing:
    repo = get_repo_or_404(repo_id)
    return repo.list_files(path, page=page, page_size=page_size)


@router.get("/file", response_model=FileContent)
def get_file(
    repo_id: str,
    path: str = Query(..., description="Repo-relative file path."),
    start_line: int | None = Query(None, ge=1),
    end_line: int | None = Query(None, ge=1),
    max_bytes: int | None = Query(None, ge=1),
) -> FileContent:
    repo = get_repo_or_404(repo_id)
    return repo.read_file(
        path, start_line=start_line, end_line=end_line, max_bytes=max_bytes
    )


@router.get("/metadata", response_model=FileMetadata)
def get_metadata(
    repo_id: str,
    path: str = Query(..., description="Repo-relative file path."),
) -> FileMetadata:
    repo = get_repo_or_404(repo_id)
    return repo.get_file_metadata(path)
