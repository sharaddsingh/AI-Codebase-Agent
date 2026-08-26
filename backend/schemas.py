"""Request/response schemas for the HTTP API.

Response bodies for repository traversal reuse the typed models from
:mod:`code_intelligence.models` directly. This module adds the request bodies
and a few response envelopes specific to the HTTP layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRepoRequest(BaseModel):
    path: str = Field(..., description="Filesystem path to the local repository root.")
    name: str | None = Field(None, description="Optional display name.")


class AgentChatRequest(BaseModel):
    repo_id: str = Field(..., description="Id of a registered repository.")
    question: str = Field(..., min_length=1, description="The natural-language question.")


class HealthResponse(BaseModel):
    status: str = "ok"
    model_provider: str
    model_configured: bool          # never the key itself — only whether one is set
    model: str
    repositories: int
    unrestricted_roots: bool


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
