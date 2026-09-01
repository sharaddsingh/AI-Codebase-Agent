"""The AI codebase agent: a bounded, tool-using investigation loop.

Public surface:
- :class:`AgentLoop` — orchestrates classify → plan → gather (tool calls) → answer.
- :class:`Budget` / :class:`BudgetTracker` — the four-axis run limits.
- :class:`ModelAdapter` and concrete :class:`AnthropicAdapter` / :class:`MockAdapter`.
- Event/result models for streaming and final output.
"""

from __future__ import annotations

from .budget import Budget, BudgetTracker
from .classifier import classify, strategy_for
from .loop import AgentLoop
from .model_adapter import (
    AnthropicAdapter,
    MockAdapter,
    ModelAdapter,
    OpenAIAdapter,
    ModelCallError,
    ModelConfigError,
    ModelResponse,
    ToolCall,
)
from .models import (
    AgentEvent,
    AgentEventType,
    AgentResult,
    TaskType,
    ToolCallRecord,
)
from .tools_spec import TOOL_SCHEMAS, execute_tool

__all__ = [
    "AgentLoop",
    "Budget",
    "BudgetTracker",
    "classify",
    "strategy_for",
    "ModelAdapter",
    "AnthropicAdapter",
    "MockAdapter",
    "OpenAIAdapter",
    "ModelResponse",
    "ModelCallError",
    "ModelConfigError",
    "ToolCall",
    "AgentEvent",
    "AgentEventType",
    "AgentResult",
    "TaskType",
    "ToolCallRecord",
    "TOOL_SCHEMAS",
    "execute_tool",
]
