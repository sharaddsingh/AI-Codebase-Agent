"""Health and readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..deps import get_registry
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        model_provider=settings.model_provider,
        model_configured=settings.model_configured,  # boolean only; never the key
        model=(
            settings.anthropic_model
            if settings.model_provider == "anthropic"
            else settings.model_provider
        ),
        repositories=len(get_registry().list()),
        unrestricted_roots=settings.allowed_roots_list() is None,
    )
