"""Provider-agnostic model adapter.

The agent loop programs against :class:`ModelAdapter` and never imports a vendor
SDK directly. :class:`AnthropicAdapter` (Claude) is the concrete provider;
a :class:`MockAdapter` replays scripted responses so the loop can be tested
deterministically without a network call or API key. :class:`OpenAIAdapter`
speaks the OpenAI Chat Completions protocol for any compatible host (OpenAI,
TaBiToken, OpenRouter, llama.cpp / vLLM / Ollama with an OpenAI shim).

The internal message format is an OpenAI-style chat schema (a de-facto
standard): a list of ``{"role", "content", ...}`` dicts, where assistant
tool-call turns carry ``tool_calls`` and tool results use
``{"role": "tool", "tool_call_id"}``. Each adapter translates this to its
provider's native format — :class:`AnthropicAdapter` maps it onto Claude's
``tool_use`` / ``tool_result`` content blocks and ``input_schema`` tools;
:class:`OpenAIAdapter` passes it through unchanged because the format is
already OpenAI's.
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


def _describe_anthropic_error(exc: BaseException, model: str, *, max_len: int = 480) -> str:
    """Render a one-line, secret-free description of an SDK/transport error.

    `str(exc)` for the common network/auth failures flattens to a near-empty
    string ("Connection error.", "Unauthorized", "Not Found", ...) that gives the
    user no way to tell what is actually wrong. This helper keeps the exception
    class, the underlying OSError (which is where the real "firewall blocked
    it" / "DNS failed" / "TLS handshake failed" lives), the model name, and the
    request URL when the SDK exposes it — and explicitly drops anything that
    could carry the `x-api-key` / Authorization header.

    When the upstream returned HTML instead of JSON (Cloudflare / generic
    gateway challenge page), the helper adds a first-class hint that the host
    likely speaks an OpenAI-compatible protocol rather than Anthropic's
    Messages API, so the user knows to switch providers instead of digging
    through Cloudflare internals.
    """
    cls = type(exc).__name__
    base = f"{cls}: {exc}"
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None) if request is not None else None
    if url is not None:
        base = f"{base} (url={url})"
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) if response is not None else None
    if status is not None:
        base = f"{base} (status={status})"
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc:
        base = f"{base} [cause: {type(cause).__name__}: {cause}]"
    # Cloudflare / generic-gateway challenge page detection: the SDK blew up
    # because the upstream returned HTML instead of JSON. The host almost
    # certainly speaks a non-Anthropic protocol (typically an OpenAI-compatible
    # gateway like TaBiToken). Surface that as a first-class hint rather than
    # leaving the user to decode "<!DOCTYPE html>".
    text = str(exc) or ""
    if "<!DOCTYPE" in text or "<html" in text.lower() or "Just a moment" in text:
        base = (
            f"{base} | the configured base URL returned HTML, not JSON - it "
            f"likely speaks an OpenAI-compatible protocol. Switch with "
            f"MODEL_PROVIDER=openai and OPENAI_BASE_URL=<the same URL>."
        )
    base = f"{base} (model={model})"
    if len(base) > max_len:
        base = base[: max_len - 1].rstrip() + "…"
    return base


class AnthropicAdapter(ModelAdapter):
    """Claude (Anthropic) provider.

    Translates the internal OpenAI-style message list into Claude's native
    ``tool_use`` / ``tool_result`` content blocks and maps the tool schemas to
    Anthropic's ``input_schema`` form. ``max_tokens`` is required by the
    Messages API, so it is a first-class constructor argument.
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
            raise ModelCallError(_describe_anthropic_error(exc, self.model)) from exc

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


class OpenAIAdapter(ModelAdapter):
    """OpenAI-compatible provider.

    Speaks the OpenAI Chat Completions protocol (``/v1/chat/completions``),
    so it works with any service that implements it: OpenAI proper,
    third-party gateways (TaBiToken, OpenRouter), and locally-served llama.cpp
    / vLLM / Ollama with an OpenAI shim. The agent loop already produces
    OpenAI-style messages and tool schemas, so this adapter is a thin wrapper -
    the translation is mostly a passthrough.

    Set ``model_provider=openai``, ``OPENAI_API_KEY=...``, and
    ``OPENAI_BASE_URL`` (only needed for non-openai.com hosts).
    """

    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ModelConfigError(
                "OPENAI_API_KEY is not configured; the agent cannot run. "
                "Set it (and, for non-OpenAI hosts, OPENAI_BASE_URL) in the "
                "backend environment. Never expose it to the frontend."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency guaranteed by requirements
            raise ModelConfigError("The 'openai' package is not installed.") from exc

        # strip duplicate trailing slashes - the SDK is strict when concatenating /chat/completions
        clean_base = base_url.rstrip("/") if base_url else None
        self._client = OpenAI(api_key=api_key, base_url=clean_base, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ModelResponse:
        # OpenAI Chat Completions prepends the system prompt as the first
        # message with role=system.
        oa_messages: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            role = m.get("role")
            if role == "system":
                oa_messages.append({"role": "system", "content": m.get("content") or ""})
                continue
            if role == "assistant":
                content = m.get("content") or ""
                tool_calls_in = m.get("tool_calls") or []
                oa_msg = {"role": "assistant", "content": content}
                if tool_calls_in:
                    oa_msg["tool_calls"] = [
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": (tc.get("function") or {}).get("name", ""),
                                "arguments": (tc.get("function") or {}).get("arguments") or "{}",
                            },
                        }
                        for tc in tool_calls_in
                    ]
                oa_messages.append(oa_msg)
                continue
            if role == "tool":
                oa_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id", ""),
                        "content": m.get("content") or "",
                    }
                )
                continue
            oa_messages.append({"role": role or "user", "content": m.get("content") or ""})

        kwargs: dict = {
            "model": self.model,
            "messages": oa_messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
        }
        if tools:
            # The agent loop emits OpenAI-style tool schemas already
            # ({"type":"function","function":{name,description,parameters}}),
            # so no transformation is needed.
            kwargs["tools"] = tools

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise ModelCallError(_describe_anthropic_error(exc, self.model)) from exc

        text_parts: list[str] = []
        final_tool_calls: list[ToolCall] = []
        finish_reason = "stop"
        usage = None

        choices = getattr(resp, "choices", None) or []
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message is not None:
                content = getattr(message, "content", None) or ""
                if content:
                    text_parts.append(content)
                for tc in getattr(message, "tool_calls", None) or []:
                    fn = getattr(tc, "function", None)
                    name = getattr(fn, "name", "") if fn is not None else ""
                    raw_args = getattr(fn, "arguments", "{}") if fn is not None else "{}"
                    try:
                        parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                        if not isinstance(parsed, dict):
                            parsed = {}
                    except (json.JSONDecodeError, TypeError):
                        parsed = {}
                    final_tool_calls.append(
                        ToolCall(
                            id=getattr(tc, "id", "") or "",
                            name=name,
                            arguments=parsed,
                        )
                    )
            finish_reason = getattr(first, "finish_reason", None) or "stop"

        u = getattr(resp, "usage", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "prompt_tokens", None),
                "output_tokens": getattr(u, "completion_tokens", None),
            }

        return ModelResponse(
            text="".join(text_parts) or None,
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )


def _sanitize_schema_for_gemini(schema):
    """Strip JSON Schema fields Gemini rejects from a tool parameter dict.

    Gemini's ``function_declarations.parameters`` schema parser is stricter
    than OpenAI's. In particular it rejects ``additionalProperties`` (which
    our internal OpenAI-style tool schemas emit everywhere with
    ``additionalProperties: false``). It also rejects a handful of other
    JSON-Schema-but-not-Gemini fields. We strip them recursively so nested
    object schemas are also clean.
    """
    if not isinstance(schema, dict):
        return schema
    unsupported = {
        "additionalProperties",
        "$schema",
        "title",
        "definitions",
        "$ref",
        "$id",
        "$comment",
    }
    out = {}
    for key, value in schema.items():
        if key in unsupported:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {pk: _sanitize_schema_for_gemini(pv) for pk, pv in value.items()}
        elif key == "items":
            out[key] = _sanitize_schema_for_gemini(value)
        elif isinstance(value, list):
            out[key] = [_sanitize_schema_for_gemini(v) for v in value]
        elif isinstance(value, dict):
            out[key] = _sanitize_schema_for_gemini(value)
        else:
            out[key] = value
    return out


class GeminiAdapter(ModelAdapter):
    """Google Gemini (native protocol) provider.

    Translates the internal OpenAI-style message list into Gemini's
    ``contents`` format and OpenAI-style tool schemas into Gemini's
    ``function_declarations``. Streaming is not used because the agent loop
    only needs a single complete() round-trip per step.

    Set ``model_provider=gemini``, ``GEMINI_API_KEY=...`` (and optionally
    ``GEMINI_MODEL``, defaults to ``gemini-2.0-flash``).
    """

    provider = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-2.0-flash",
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ModelConfigError(
                "GEMINI_API_KEY is not configured; the agent cannot run. "
                "Set it in the backend environment (never expose it to the frontend)."
            )
        try:
            from google import genai  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - dependency declared in requirements
            raise ModelConfigError("The 'google-genai' package is not installed.") from exc

        # http_options lets us cap the request timeout so a stuck Gemini call
        # does not block the agent stream forever. The SDK accepts a float
        # timeout in seconds.
        try:
            from google.genai import types as _gtypes  # type: ignore[import-not-found]
            self._client = genai.Client(
                api_key=api_key,
                http_options=_gtypes.HttpOptions(timeout=timeout * 1000),
            )
        except Exception:  # noqa: BLE001 - older SDKs may not expose HttpOptions
            self._client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def _to_gemini_contents(self, messages: list[dict]) -> list[dict]:
        """Convert the internal OpenAI-style messages into Gemini ``contents``.

        - ``system`` messages are dropped (passed via ``system_instruction``).
        - ``user`` / assistant text become single-part text contents.
        - ``assistant`` tool-call turns become a ``model`` content with text
          (if any) plus one ``function_call`` part per tool.
        - ``tool`` result messages become ``user`` contents with one
          ``function_response`` part per result.
        """
        out: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "assistant":
                parts: list[dict] = []
                content = m.get("content")
                if content:
                    parts.append({"text": content})
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    except (json.JSONDecodeError, TypeError):
                        parsed = {}
                    parts.append({"function_call": {"name": name, "args": parsed or {}}})
                out.append({"role": "model", "parts": parts or [{"text": ""}]})
                continue
            if role == "tool":
                # The internal message format only carries tool_call_id; look
                # up the function name from the latest assistant turn that
                # emitted the matching tool call.
                call_id = m.get("tool_call_id") or ""
                fn_name = ""
                for prev in reversed(out):
                    if prev.get("role") == "model":
                        for p2 in prev.get("parts") or []:
                            fc = p2.get("function_call") if isinstance(p2, dict) else None
                            if fc and (fc.get("name") and call_id.startswith(fc.get("name", ""))):
                                fn_name = fc.get("name") or ""
                                break
                        if fn_name:
                            break
                out.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": fn_name,
                            "response": {"result": m.get("content") or ""},
                        }
                    }],
                })
                continue
            # default: treat as user text
            out.append({"role": "user", "parts": [{"text": m.get("content") or ""}]})
        return out

    def _to_gemini_tools(self, tools: list[dict]) -> list[dict]:
        """Map OpenAI-style tool schemas to Gemini ``function_declarations``.

        Gemini rejects several JSON Schema fields our OpenAI adapter emits,
        so every parameter dict is run through ``_sanitize_schema_for_gemini``
        to drop ``additionalProperties`` and friends before being sent.
        """
        declarations: list[dict] = []
        for t in tools or []:
            fn = t.get("function", t)
            declarations.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": _sanitize_schema_for_gemini(
                    fn.get("parameters") or {"type": "object", "properties": {}}
                ),
            })
        return [{"function_declarations": declarations}]

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ModelResponse:
        from google.genai import types as _gtypes  # type: ignore[import-not-found]

        config = _gtypes.GenerateContentConfig(
            system_instruction=system or None,
            temperature=temperature,
            max_output_tokens=self.max_tokens,
        )
        if tools:
            config.tools = self._to_gemini_tools(tools)

        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=self._to_gemini_contents(messages),
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise ModelCallError(_describe_anthropic_error(exc, self.model)) from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        finish_reason = "stop"

        candidates = getattr(resp, "candidates", None) or []
        if candidates:
            first = candidates[0]
            content = getattr(first, "content", None)
            parts = getattr(content, "parts", None) if content is not None else None
            for part in parts or []:
                text = getattr(part, "text", None)
                if text:
                    text_parts.append(text)
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    name = getattr(fc, "name", "") or ""
                    args = getattr(fc, "args", None) or {}
                    if not isinstance(args, dict):
                        args = {}
                    tool_calls.append(
                        ToolCall(
                            id=f"{name}_{len(tool_calls) + 1}",
                            name=name,
                            arguments=args,
                        )
                    )
            finish_reason = getattr(first, "finish_reason", None) or "stop"

        usage = None
        u = getattr(resp, "usage_metadata", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "prompt_token_count", None),
                "output_tokens": getattr(u, "candidates_token_count", None),
            }

        return ModelResponse(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
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
