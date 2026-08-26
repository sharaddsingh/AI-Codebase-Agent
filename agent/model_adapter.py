"""Provider-agnostic model adapter.

The agent loop programs against :class:`ModelAdapter` and never imports a vendor
SDK directly. :class:`AnthropicAdapter` (Claude) is the concrete provider; a
:class:`MockAdapter` replays scripted responses so the loop can be tested
deterministically without a network call or API key.

The internal message format is an OpenAI-style chat schema (a de-facto
standard): a list of ``{"role", "content", ...}`` dicts, where assistant
tool-call turns carry ``tool_calls`` and tool results use
``{"role": "tool", "tool_call_id"}``. Each adapter translates this to its
provider's native format — :class:`AnthropicAdapter` maps it onto Claude's
``tool_use`` / ``tool_result`` content blocks and ``input_schema`` tools.
"""

from __future__ import annotations

import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ModelConfigError(RuntimeError):
    """Raised when a provider cannot be constructed (e.g. missing API key)."""


class ModelCallError(RuntimeError):
    """Raised when a model call fails at runtime (network, auth, rate limit)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict | None = None


class ModelAdapter(ABC):
    provider: str = "abstract"
    model: str = "unknown"

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ModelResponse:
        """One model round-trip. Returns text and/or requested tool calls."""


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Map OpenAI-style ``{"type":"function","function":{...}}`` schemas to
    Anthropic tool definitions (``name`` / ``description`` / ``input_schema``)."""

    out: list[dict] = []
    for t in tools:
        fn = t.get("function", t)
        out.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    return out


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """Convert the internal OpenAI-style message list into Anthropic's content-
    block format, merging consecutive same-role turns so roles strictly
    alternate (as the Messages API requires).

    - ``system`` messages are dropped (passed as a top-level parameter instead).
    - ``assistant`` turns become text and/or ``tool_use`` blocks.
    - ``tool`` results become ``tool_result`` blocks on a ``user`` turn, so all
      results answering one assistant tool-call turn group into a single user
      message.
    """

    out: list[dict] = []

    def push(role: str, block: dict) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].append(block)
        else:
            out.append({"role": role, "content": [block]})

    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "user":
            push("user", {"type": "text", "text": m.get("content") or ""})
        elif role == "assistant":
            content = m.get("content")
            if content:
                push("assistant", {"type": "text", "text": content})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw)
                    if not isinstance(args, dict):
                        args = {}
                except (json.JSONDecodeError, TypeError):
                    args = {}
                push(
                    "assistant",
                    {"type": "tool_use", "id": tc.get("id", ""), "name": fn.get("name", ""), "input": args},
                )
        elif role == "tool":
            push(
                "user",
                {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m.get("content") or "",
                },
            )
    return out


def _create_accepts(client, param: str) -> bool:
    """True if this SDK's ``messages.create()`` accepts the given keyword.

    Different ``anthropic`` SDK generations expose different typed parameters
    (newer builds dropped ``temperature`` from the signature). We inspect once
    and send only kwargs the installed SDK will actually accept, instead of
    hard-coding a parameter set that breaks across versions.
    """
    try:
        params = inspect.signature(client.messages.create).parameters
    except (TypeError, ValueError):  # pragma: no cover - unusual builtins
        return True  # assume supported (matches older real SDKs)
    if param in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


class AnthropicAdapter(ModelAdapter):
    """Claude (Anthropic) provider.

    Translates the internal OpenAI-style message list into Claude's native
    ``tool_use`` / ``tool_result`` content blocks and maps the tool schemas to
    Anthropic's ``input_schema`` form. ``max_tokens`` is required by the Messages
    API, so it is a first-class constructor argument.
    """

    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "claude-opus-5",
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ModelConfigError(
                "ANTHROPIC_API_KEY is not configured; the agent cannot run. "
                "Set it in the backend environment (never expose it to the frontend)."
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - dependency guaranteed by requirements
            raise ModelConfigError("The 'anthropic' package is not installed.") from exc

        self._client = Anthropic(api_key=api_key, base_url=base_url or None, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens
        # Some anthropic SDK generations dropped `temperature` from create()'s
        # typed signature; detect support so we never pass a rejected kwarg.
        self._supports_temperature = _create_accepts(self._client, "temperature")

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ModelResponse:
        kwargs: dict = {
            "model": self.model,
            "system": system,
            "messages": _to_anthropic_messages(messages),
            "max_tokens": self.max_tokens,
        }
        if self._supports_temperature:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise ModelCallError(str(exc)) from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(resp, "content", None) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif btype == "tool_use":
                raw = getattr(block, "input", None)
                args = raw if isinstance(raw, dict) else {}
                tool_calls.append(
                    ToolCall(
                        id=getattr(block, "id", "") or "",
                        name=getattr(block, "name", "") or "",
                        arguments=args,
                    )
                )

        usage = None
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None),
            }

        return ModelResponse(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            finish_reason=getattr(resp, "stop_reason", None) or "stop",
            usage=usage,
        )


class MockAdapter(ModelAdapter):
    """Replays a fixed list of :class:`ModelResponse` objects, ignoring input.

    Used by tests to drive the agent loop through deterministic tool-call and
    answer sequences. Records every call for assertions.
    """

    provider = "mock"

    def __init__(self, responses: list[ModelResponse], model: str = "mock-model") -> None:
        self._responses = list(responses)
        self.model = model
        self.calls: list[dict] = []

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ModelResponse:
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if not self._responses:
            return ModelResponse(text="(mock: no scripted response left)", tool_calls=[])
        return self._responses.pop(0)


def tool_call(name: str, arguments: dict, call_id: str = "call_1") -> ModelResponse:
    """Convenience for tests: a response that requests a single tool call."""

    return ModelResponse(text=None, tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)])


def final_answer(text: str) -> ModelResponse:
    """Convenience for tests: a response that is a final answer (no tool calls)."""

    return ModelResponse(text=text, tool_calls=[])
