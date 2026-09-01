"""Shared dependencies: the repository registry and the model adapter.

These are process-wide singletons. Tests can inject a scripted
:class:`~agent.MockAdapter` via :func:`set_model_adapter` so the agent endpoint
runs deterministically without an API key.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent import AgentLoop, AnthropicAdapter, MockAdapter, ModelAdapter, OpenAIAdapter
from agent.model_adapter import ModelConfigError
from code_intelligence.registry import RepositoryRegistry
from code_intelligence.repository import RepositoryInterface

from .config import Settings, get_settings
from .github_repos_state import discover_github_repos
from .uploaded_repos import UploadLimits, discover_uploaded_repos

log = logging.getLogger("backend.deps")

_registry: RepositoryRegistry | None = None
_model_adapter_override: ModelAdapter | None = None


def get_registry() -> RepositoryRegistry:
    global _registry
    if _registry is None:
        s = get_settings()
        _registry = RepositoryRegistry(
            github_token=s.github_token,
            github_mcp_url=s.github_mcp_url,
            github_mcp_toolsets=s.github_mcp_toolsets,
            github_mcp_timeout=s.github_mcp_timeout,
        )
    return _registry


def set_registry(registry: RepositoryRegistry | None) -> None:
    """Override the repository registry (used by tests to inject a registry whose
    GitHub MCP client is backed by an in-process fake MCP server). Pass None to
    clear. Any previously-installed registry has its GitHub MCP session closed so
    its loop thread does not leak."""
    global _registry
    if _registry is not None and _registry is not registry:
        try:
            _registry.close_github_mcp()
        except Exception:  # noqa: S110 - best-effort cleanup
            pass
    _registry = registry


def get_repo_or_404(repo_id: str) -> RepositoryInterface:
    # RepositoryRegistry.get raises RepositoryNotFoundError (mapped to HTTP 404
    # by the app's exception handler) when the id is unknown.
    return get_registry().get(repo_id)


def set_model_adapter(adapter: ModelAdapter | None) -> None:
    """Override the model adapter (used by tests). Pass None to clear."""
    global _model_adapter_override
    _model_adapter_override = adapter


def build_model_adapter(settings: Settings) -> ModelAdapter:
    """Construct the configured model adapter. May raise ModelConfigError.

    The selection is based on the lowercased model_provider so that values like
    `MODEL_PROVIDER=OPENAI` from Render/Vercel env dashboards still resolve
    correctly.
    """
    provider = settings.model_provider_normalized
    if provider == "mock":
        return MockAdapter([])
    if provider == "openai":
        # Any OpenAI-compatible chat-completions service. Set OPENAI_BASE_URL
        # for non-openai.com hosts (TaBiToken, OpenRouter, llama.cpp + shim,
        # vLLM, etc.). The adapter sends OpenAI-style messages and tools,
        # which is exactly what those services expect.
        return OpenAIAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            max_tokens=settings.openai_max_tokens,
        )
    if provider == "anthropic":
        return AnthropicAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            base_url=settings.anthropic_base_url,
            max_tokens=settings.anthropic_max_tokens,
        )
    raise ModelConfigError(
        f"Unknown MODEL_PROVIDER: {settings.model_provider!r}. "
        "Expected one of: anthropic, openai, mock."
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
    if _registry is not None:
        try:
            _registry.close_github_mcp()
        except Exception:  # noqa: S110 - best-effort cleanup
            pass
    _registry = None
    _model_adapter_override = None


def get_upload_root() -> Path:
    """Resolved on-disk root the upload pipeline writes to.

    Defaults to ``./uploaded_repos`` and is created on first upload. The
    caller is responsible for ensuring the path lives somewhere the process
    can write to (the default sits next to the project root).
    """

    return Path(get_settings().upload_root).resolve()


def upload_limits() -> UploadLimits:
    """Per-upload caps, from ``UPLOAD_MAX_*`` in the environment."""

    s = get_settings()
    return UploadLimits(
        max_total_bytes=s.upload_max_total_mb * 1024 * 1024,
        max_file_bytes=s.upload_max_file_mb * 1024 * 1024,
        max_files=s.upload_max_files,
    )


def rehydrate_uploads() -> int:
    """Re-register uploaded folders that a previous process left on disk.

    The registry is in-memory but the uploads are not, so without this a
    backend restart — a code edit under ``--reload``, a container redeploy —
    silently forgets every uploaded repo while its files sit right there in the
    upload root. The browser keeps showing those repos and every request for
    one fails with "No repository registered with id ...", *including* the
    DELETE that would have cleared it, which leaves the UI wedged.

    Re-registering is enough to make the browser's ids valid again: an uploaded
    repo's id is derived from its resolved directory path (see
    ``code_intelligence.registry._repo_id_for``), so a revived repo comes back
    with exactly the id the frontend is still holding.

    Returns the number of repos revived. Directories are handled independently
    and failures are logged, not raised: one unreadable folder must never stop
    the server from starting.
    """

    root = get_upload_root()
    registry = get_registry()
    revived = 0
    for repo_dir, name in discover_uploaded_repos(root):
        try:
            registry.register_uploaded(repo_dir, name=name)
        except Exception:  # noqa: BLE001 - one bad directory must not block startup
            log.warning("could not restore uploaded repo %s", repo_dir.name, exc_info=True)
            continue
        revived += 1
    return revived

def rehydrate_github_repos() -> int:
    """Re-register GitHub repositories that a previous process persisted.

    The registry is in-memory and the GitHub MCP session dies with the
    process, so without this a backend restart (--reload, redeploy, orphan-
    worker swap) wipes every GitHub registration while the frontend keeps
    holding the same deterministic repo_<sha> id. Every subsequent DELETE /
    file-tree call would 404 with 'No repository registered with id ...'.

    We mirror the design of rehydrate_uploads: read every persisted entry,
    call RepositoryRegistry.register_github for each, and swallow individual
    failures so one bad URL cannot block startup. The deterministic id
    (sha256 of owner/repo) means re-registering the same URL after a restart
    always produces the same row the frontend already has.
    """

    root = get_upload_root()
    registry = get_registry()
    revived = 0
    for stored in discover_github_repos(root):
        try:
            registry.register_github(stored.url, name=stored.name)
        except Exception:  # noqa: BLE001 - one bad URL must not block startup
            log.warning(
                "could not restore github repo %s",
                stored.url,
                exc_info=True,
            )
            continue
        revived += 1
    return revived
