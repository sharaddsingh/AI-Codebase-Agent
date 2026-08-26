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
