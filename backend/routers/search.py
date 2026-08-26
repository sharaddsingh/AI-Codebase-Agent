"""Lexical code-search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query

from code_intelligence.models import SearchResults

from ..deps import get_repo_or_404

router = APIRouter(prefix="/repositories/{repo_id}", tags=["search"])


@router.get("/search", response_model=SearchResults)
def search_code(
    repo_id: str,
    query: str = Query(..., min_length=1),
    regex: bool = Query(False),
    case_sensitive: bool = Query(False),
    path_glob: str | None = Query(None),
    max_results: int | None = Query(None, ge=1),
) -> SearchResults:
    repo = get_repo_or_404(repo_id)
    return repo.search_code(
        query,
        regex=regex,
        case_sensitive=case_sensitive,
        path_glob=path_glob,
        max_results=max_results,
    )
