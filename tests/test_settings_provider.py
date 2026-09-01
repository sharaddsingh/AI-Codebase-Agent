"""Regression tests for Settings.model_configured and adapter dispatch.

The Vercel + Render env dashboards happily accept `MODEL_PROVIDER=OPENAI`
and `MODEL_PROVIDER=OpenAI`. Before the fix the backend treated those
strings as unknown providers, `model_configured` reported False, the UI
disabled the agent textarea, and the model pill showed "OPENAI * OPENAI"
(both provider and model fell back to the provider string).

These tests pin both pieces of behaviour so a regression is loud.
"""

from __future__ import annotations

import pytest

import pytest

try:
    import openai  # noqa: F401
    _HAS_OPENAI = True
except ImportError:  # pragma: no cover - exercised in sandbox
    _HAS_OPENAI = False

from backend.config import Settings
from backend.deps import build_model_adapter
from agent import MockAdapter, OpenAIAdapter, AnthropicAdapter
from agent.model_adapter import ModelConfigError


def test_model_configured_openai_lowercase() -> None:
    s = Settings(model_provider="openai", openai_api_key="sk-test")
    assert s.model_configured is True
    assert s.model_provider_normalized == "openai"


def test_model_configured_openai_uppercase() -> None:
    """Render / Vercel store env vars verbatim; uppercase must work."""
    s = Settings(model_provider="OPENAI", openai_api_key="sk-test")
    assert s.model_configured is True
    assert s.model_provider_normalized == "openai"


def test_model_configured_openai_mixed_case() -> None:
    s = Settings(model_provider="OpenAI", openai_api_key="sk-test")
    assert s.model_configured is True
    assert s.model_provider_normalized == "openai"


def test_model_configured_openai_without_key() -> None:
    s = Settings(model_provider="openai", openai_api_key=None)
    assert s.model_configured is False


def test_model_configured_anthropic_unchanged() -> None:
    s = Settings(model_provider="anthropic", anthropic_api_key="sk-test")
    assert s.model_configured is True


def test_model_configured_mock_unchanged() -> None:
    s = Settings(model_provider="mock")
    assert s.model_configured is True


def test_model_configured_unknown_provider_is_false() -> None:
    s = Settings(model_provider="bogus")
    assert s.model_configured is False


@pytest.mark.skipif(not _HAS_OPENAI, reason="openai package not installed")
def test_build_model_adapter_openai_uppercase() -> None:
    s = Settings(model_provider="OPENAI", openai_api_key="sk-test")
    adapter = build_model_adapter(s)
    assert isinstance(adapter, OpenAIAdapter)


def test_build_model_adapter_unknown_provider_still_errors() -> None:
    s = Settings(model_provider="bogus")
    with pytest.raises(ModelConfigError):
        build_model_adapter(s)


def test_build_model_adapter_mock_unchanged() -> None:
    s = Settings(model_provider="mock")
    assert isinstance(build_model_adapter(s), MockAdapter)
