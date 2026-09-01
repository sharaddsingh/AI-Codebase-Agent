"""Health and readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..deps import get_registry
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    provider = settings.model_provider_normalized
    if provider == "openai":
        model_name = settings.openai_model
    elif provider == "anthropic":
        model_name = settings.anthropic_model
    elif provider == "gemini":
        model_name = settings.gemini_model
    elif provider == "mock":
        model_name = "mock"
    else:
        model_name = settings.model_provider
    return HealthResponse(
        model_provider=settings.model_provider,
        model_configured=settings.model_configured,  # boolean only; never the key
        model=model_name,
        repositories=len(get_registry().list()),
    )
