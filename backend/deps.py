"""Shared dependencies: the repository registry and the model adapter.

These are process-wide singletons. Tests can inject a scripted
:class:`~agent.MockAdapter` via :func:`set_model_adapter` so the agent endpoint
runs deterministically without an API key.
"""

from __future__ import annotations

from agent import AgentLoop, AnthropicAdapter, MockAdapter, ModelAdapter
from code_intelligence.registry import RepositoryRegistry
from code_intelligence.repository import RepositoryInterface

from .config import Settings, get_settings

_registry: RepositoryRegistry | None = None
_model_adapter_override: ModelAdapter | None = None


def get_registry() -> RepositoryRegistry:
    global _registry
    if _registry is None:
        s = get_settings()
        _registry = RepositoryRegistry(
            allowed_roots=s.allowed_roots_list(),
            respect_gitignore=s.respect_gitignore,
        )
    return _registry


def get_repo_or_404(repo_id: str) -> RepositoryInterface:
    # RepositoryRegistry.get raises RepositoryNotFoundError (mapped to HTTP 404
    # by the app's exception handler) when the id is unknown.
    return get_registry().get(repo_id)


def set_model_adapter(adapter: ModelAdapter | None) -> None:
    """Override the model adapter (used by tests). Pass None to clear."""
    global _model_adapter_override
    _model_adapter_override = adapter


def build_model_adapter(settings: Settings) -> ModelAdapter:
    """Construct the configured model adapter. May raise ModelConfigError."""
    if settings.model_provider == "mock":
        return MockAdapter([])
    return AnthropicAdapter(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        base_url=settings.anthropic_base_url,
        max_tokens=settings.anthropic_max_tokens,
    )


def get_model_adapter() -> ModelAdapter:
    if _model_adapter_override is not None:
        return _model_adapter_override
    return build_model_adapter(get_settings())


def get_agent_loop() -> AgentLoop:
    s = get_settings()
    return AgentLoop(get_model_adapter(), budget=s.budget(), temperature=s.agent_temperature)


def reset_state() -> None:
    """Reset singletons (used by tests)."""
    global _registry, _model_adapter_override
    _registry = None
    _model_adapter_override = None
