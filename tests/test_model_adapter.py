"""AnthropicAdapter: message/tool translation and response parsing.

These tests exercise the OpenAI-style → Anthropic translation and the response
parsing with NO network and NO real API key — a fake client is injected after
construction. They lock in the contract the agent loop depends on: strict
user/assistant alternation, tool_use/tool_result blocks, and system passed as a
top-level parameter.
"""

from __future__ import annotations

import pytest

from agent.model_adapter import (
    AnthropicAdapter,
    ModelConfigError,
    _create_accepts,
    _to_anthropic_messages,
    _to_anthropic_tools,
)
from agent.tools_spec import TOOL_SCHEMAS

# OpenAIAdapter requires the openai SDK, which the runtime requirements
# pin but may be missing in a minimal dev env. Skip those tests cleanly when
# the package isn't there rather than failing the suite.
try:
    import openai  # noqa: F401
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False


# -- fakes standing in for the anthropic SDK response objects ------------------
class _Block:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Resp:
    def __init__(self, content, stop_reason, usage) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


class _Messages:
    def __init__(self, resp, sink) -> None:
        self._resp = resp
        self._sink = sink

    def create(self, **kwargs):
        self._sink.append(kwargs)
        return self._resp


class _FakeClient:
    def __init__(self, resp, sink) -> None:
        self.messages = _Messages(resp, sink)


def _adapter_with(resp):
    """A constructed AnthropicAdapter whose SDK client is replaced by a fake."""
    sink: list[dict] = []
    adapter = AnthropicAdapter(api_key="sk-test", model="claude-opus-5", max_tokens=1234)
    adapter._client = _FakeClient(resp, sink)
    # Recompute against the fake (its create() takes **kwargs → accepts temperature).
    adapter._supports_temperature = _create_accepts(adapter._client, "temperature")
    return adapter, sink


# -- construction --------------------------------------------------------------
def test_missing_api_key_raises_config_error() -> None:
    with pytest.raises(ModelConfigError):
        AnthropicAdapter(api_key=None)


# -- tool schema conversion ----------------------------------------------------
def test_tool_schema_conversion_to_input_schema() -> None:
    converted = _to_anthropic_tools(TOOL_SCHEMAS)
    assert converted, "expected at least one tool"
    for t in converted:
        assert set(t) == {"name", "description", "input_schema"}
        assert "function" not in t
        assert t["input_schema"]["type"] == "object"


# -- message translation -------------------------------------------------------
def test_message_translation_blocks_and_merging() -> None:
    messages = [
        {"role": "user", "content": "question"},
        {
            "role": "assistant",
            "content": "let me look",
            "tool_calls": [
                {"id": "c1", "function": {"name": "search_code", "arguments": '{"query": "x"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "RESULT"},
        # The loop appends the force-answer nudge as a separate user message; it
        # must merge with the tool-result user turn so roles keep alternating.
        {"role": "user", "content": "ANSWER NOW"},
    ]
    out = _to_anthropic_messages(messages)

    assert [m["role"] for m in out] == ["user", "assistant", "user"]

    assistant_blocks = out[1]["content"]
    assert assistant_blocks[0] == {"type": "text", "text": "let me look"}
    assert assistant_blocks[1]["type"] == "tool_use"
    assert assistant_blocks[1]["id"] == "c1"
    assert assistant_blocks[1]["name"] == "search_code"
    assert assistant_blocks[1]["input"] == {"query": "x"}

    final_blocks = out[2]["content"]
    assert final_blocks[0]["type"] == "tool_result"
    assert final_blocks[0]["tool_use_id"] == "c1"
    assert final_blocks[0]["content"] == "RESULT"
    assert final_blocks[1] == {"type": "text", "text": "ANSWER NOW"}


def test_system_dropped_and_bad_tool_json_becomes_empty() -> None:
    messages = [
        {"role": "system", "content": "handled as a top-level param, not a message"},
        {
            "role": "assistant",
            "content": "",  # empty text must not emit a text block
            "tool_calls": [
                {"id": "c1", "function": {"name": "read_file", "arguments": "not-json"}},
            ],
        },
    ]
    out = _to_anthropic_messages(messages)
    assert [m["role"] for m in out] == ["assistant"]
    blocks = out[0]["content"]
    assert len(blocks) == 1
    assert blocks[0]["type"] == "tool_use"
    assert blocks[0]["input"] == {}  # unparseable arguments degrade to {}


# -- response parsing + request shape ------------------------------------------
def test_complete_parses_text_tool_use_and_usage() -> None:
    resp = _Resp(
        content=[
            _Block(type="text", text="hello "),
            _Block(type="text", text="world"),
            _Block(type="tool_use", id="tu_1", name="read_file", input={"path": "a.py"}),
        ],
        stop_reason="tool_use",
        usage=_Usage(10, 5),
    )
    adapter, sink = _adapter_with(resp)

    out = adapter.complete(
        system="SYSTEM PROMPT",
        messages=[{"role": "user", "content": "hi"}],
        tools=TOOL_SCHEMAS,
        temperature=0.0,
    )

    # concatenated text, tool call, finish reason, usage
    assert out.text == "hello world"
    assert out.finish_reason == "tool_use"
    assert out.usage == {"input_tokens": 10, "output_tokens": 5}
    assert len(out.tool_calls) == 1
    tc = out.tool_calls[0]
    assert (tc.id, tc.name, tc.arguments) == ("tu_1", "read_file", {"path": "a.py"})

    # request shape: system is a top-level param, max_tokens forwarded, tools converted
    sent = sink[0]
    assert sent["system"] == "SYSTEM PROMPT"
    assert sent["max_tokens"] == 1234
    assert sent["model"] == "claude-opus-5"
    assert sent["temperature"] == 0.0  # sent because the fake create() accepts it
    assert "function" not in sent["tools"][0]
    assert sent["tools"][0]["input_schema"]["type"] == "object"


def test_temperature_omitted_when_sdk_rejects_it() -> None:
    # A newer-SDK-style create() whose signature lacks `temperature` and has no
    # **kwargs — passing temperature would raise TypeError (the reported bug).
    class _StrictMessages:
        def create(self, *, model, system, messages, max_tokens, tools=None):
            self.received = {"model": model, "max_tokens": max_tokens}
            return _Resp(
                content=[_Block(type="text", text="ok")],
                stop_reason="end_turn",
                usage=_Usage(1, 1),
            )

    class _StrictClient:
        def __init__(self) -> None:
            self.messages = _StrictMessages()

    adapter = AnthropicAdapter(api_key="sk-test", max_tokens=10)
    adapter._client = _StrictClient()
    adapter._supports_temperature = _create_accepts(adapter._client, "temperature")
    assert adapter._supports_temperature is False

    # Must not raise even though the loop always passes temperature.
    out = adapter.complete(system="s", messages=[{"role": "user", "content": "q"}], temperature=0.0)
    assert out.text == "ok"


def test_complete_text_only_answer_has_no_tool_calls() -> None:
    resp = _Resp(
        content=[_Block(type="text", text="final answer")],
        stop_reason="end_turn",
        usage=_Usage(3, 2),
    )
    adapter, _ = _adapter_with(resp)
    out = adapter.complete(system="s", messages=[{"role": "user", "content": "q"}])
    assert out.text == "final answer"
    assert out.tool_calls == []
    assert out.finish_reason == "end_turn"


# --------------------------------------------------------------------------
# HTML / Cloudflare detection in the shared error helper.
# --------------------------------------------------------------------------

class _FakeExc(Exception):
    """Minimal stand-in for the anthropic SDK's auth/network exceptions."""

    def __init__(self, msg: str, status: int = 403) -> None:
        super().__init__(msg)
        self.request = _FakeReq(f"https://tabitoken.com/v1/messages")
        self.response = _FakeResp(status)


class _FakeReq:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeResp:
    def __init__(self, status: int) -> None:
        self.status_code = status


def test_describe_anthropic_error_detects_cloudflare_html() -> None:
    """When the upstream returns HTML (Cloudflare challenge), the helper must
    add a first-class hint to switch to MODEL_PROVIDER=openai."""

    from agent.model_adapter import _describe_anthropic_error

    msg = "<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
    exc = _FakeExc(msg)
    out = _describe_anthropic_error(exc, "claude-opus-5")
    assert "HTML, not JSON" in out
    assert "MODEL_PROVIDER=openai" in out
    # And never leaks any token-like secret.
    assert "x-api-key" not in out
    assert "sk-" not in out


def test_describe_anthropic_error_passes_through_normal_errors() -> None:
    """Non-HTML errors should not get the OpenAI-switch hint."""

    from agent.model_adapter import _describe_anthropic_error

    exc = _FakeExc("Connection refused", status=0)
    out = _describe_anthropic_error(exc, "claude-opus-5")
    assert "MODEL_PROVIDER=openai" not in out
    assert "claude-opus-5" in out


# --------------------------------------------------------------------------
# OpenAIAdapter: passthrough translation + error surfacing.
# --------------------------------------------------------------------------

def test_openai_adapter_rejects_missing_key() -> None:
    from agent.model_adapter import OpenAIAdapter

    with pytest.raises(ModelConfigError) as ei:
        OpenAIAdapter(api_key=None)
    assert "OPENAI_API_KEY" in str(ei.value)


@pytest.mark.skipif(not _HAS_OPENAI, reason="openai package not installed")
def test_openai_adapter_passes_messages_and_tools_to_sdk() -> None:
    """Smoke test the passthrough against a fake OpenAI SDK client."""
    from agent.model_adapter import OpenAIAdapter

    captured: dict = {}

    class _ChoiceMsg:
        content = "hi"
        tool_calls = []

    class _Choice:
        def __init__(self) -> None:
            self.message = _ChoiceMsg()
            self.finish_reason = "stop"

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 2

    class _Resp:
        def __init__(self) -> None:
            self.choices = [_Choice()]
            self.usage = _Usage()

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    class _Client:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": _Completions()})()

    adapter = OpenAIAdapter(api_key="sk-test", model="gpt-4o-mini")
    adapter._client = _Client()
    out = adapter.complete(
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        tools=[{"type": "function", "function": {"name": "x", "parameters": {}}}],
        temperature=0.0,
    )
    # system prompt is prepended as a system message.
    assert captured["messages"][0] == {"role": "system", "content": "sys"}
    # tools passed through.
    assert captured["tools"] == [{"type": "function", "function": {"name": "x", "parameters": {}}}]
    # response parsed.
    assert out.text == "hi"
    assert out.finish_reason == "stop"
    assert out.usage == {"input_tokens": 1, "output_tokens": 2}


@pytest.mark.skipif(not _HAS_OPENAI, reason="openai package not installed")
def test_openai_adapter_parses_tool_calls() -> None:
    from agent.model_adapter import OpenAIAdapter
    import json as _json

    class _ToolCall:
        def __init__(self, id_: str, name: str, args: str) -> None:
            self.id = id_
            self.function = type("F", (), {"name": name, "arguments": args})()

    class _ChoiceMsg:
        content = None
        tool_calls = [
            _ToolCall("c1", "search_code", _json.dumps({"query": "auth"})),
        ]

    class _Choice:
        def __init__(self) -> None:
            self.message = _ChoiceMsg()
            self.finish_reason = "tool_calls"

    class _Resp:
        def __init__(self) -> None:
            self.choices = [_Choice()]
            self.usage = None

    class _Completions:
        def create(self, **kwargs):
            return _Resp()

    class _Client:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": _Completions()})()

    adapter = OpenAIAdapter(api_key="sk-test")
    adapter._client = _Client()
    out = adapter.complete(
        system="s",
        messages=[
            {"role": "user", "content": "u"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "old", "function": {"name": "x", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "old", "content": "r"},
        ],
    )
    assert out.tool_calls and out.tool_calls[0].name == "search_code"
    assert out.tool_calls[0].arguments == {"query": "auth"}
    assert out.finish_reason == "tool_calls"


def test_sanitize_schema_for_gemini_strips_additional_properties() -> None:
    from agent.model_adapter import _sanitize_schema_for_gemini

    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "title": "Path"},
            "options": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "additionalProperties": False,
                "title": "Options",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#",
    }
    clean = _sanitize_schema_for_gemini(schema)
    # Gemini rejects these fields at every level of nesting.
    assert "additionalProperties" not in clean
    assert "additionalProperties" not in clean["properties"]["options"]
    assert "title" not in clean["properties"]["options"]
    assert "$schema" not in clean
    # Real schema content survives.
    assert set(clean["properties"].keys()) == {"path", "options"}
    assert clean["required"] == ["path"]
    assert clean["properties"]["path"]["type"] == "string"


def test_sanitize_schema_for_gemini_handles_non_dict() -> None:
    from agent.model_adapter import _sanitize_schema_for_gemini

    # Defensive: a missing/None parameters dict should fall back to the empty
    # object schema, not crash the request.
    assert _sanitize_schema_for_gemini(None) is None
    assert _sanitize_schema_for_gemini({"type": "object"}) == {"type": "object"}


def test_assistant_message_round_trips_provider_meta() -> None:
    from agent.loop import _assistant_tool_call_message
    from agent.model_adapter import ModelResponse, ToolCall

    resp = ModelResponse(
        text=None,
        tool_calls=[
            ToolCall(
                id="call_1",
                name="list_files",
                arguments={"path": "."},
                provider_meta={"thought_signature": "sig-abc"},
            )
        ],
    )
    msg = _assistant_tool_call_message(resp)
    assert msg["role"] == "assistant"
    assert len(msg["tool_calls"]) == 1
    tc = msg["tool_calls"][0]
    # Stored under underscore-prefixed key so non-Gemini adapters ignore it.
    assert tc["_thought_signature"] == "sig-abc"
    assert tc["function"]["name"] == "list_files"


def test_assistant_message_omits_metadata_when_none() -> None:
    from agent.loop import _assistant_tool_call_message
    from agent.model_adapter import ModelResponse, ToolCall

    resp = ModelResponse(
        text=None,
        tool_calls=[ToolCall(id="call_1", name="noop", arguments={})],
    )
    msg = _assistant_tool_call_message(resp)
    tc = msg["tool_calls"][0]
    # No metadata -> no underscore-prefixed keys appear.
    assert not any(k.startswith("_") for k in tc.keys())

