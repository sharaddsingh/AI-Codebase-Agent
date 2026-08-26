"""Typed models for the agent: streaming events, budgets, and the final result."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from code_intelligence.models import Citation


class TaskType(str, Enum):
    """Coarse classification that shapes the investigation strategy."""

    how_it_works = "how_it_works"          # "How does authentication work?"
    find_usages = "find_usages"            # "Where is this function used?"
    debug = "debug"                        # "Why might this endpoint return 401?"
    change_impact = "change_impact"        # "What files would change to add X?"
    general = "general"


class AgentEventType(str, Enum):
    status = "status"          # human-readable progress line
    classified = "classified"  # task classification result
    plan = "plan"              # the strategy the agent will follow
    tool_call = "tool_call"    # the agent invoked a tool
    tool_result = "tool_result"  # a bounded summary of a tool result
    token = "token"  # noqa: S105 - enum member label (a stream event kind), not a secret
    answer = "answer"          # final answer + citations
    error = "error"            # a recoverable or terminal error
    budget = "budget"          # a budget limit was reached
    done = "done"              # stream terminator


class AgentEvent(BaseModel):
    type: AgentEventType
    message: str | None = None
    data: dict | None = None
    step: int | None = None


class ToolCallRecord(BaseModel):
    step: int
    name: str
    arguments: dict
    ok: bool
    summary: str
    error: str | None = None


class AgentResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    task_type: TaskType = TaskType.general
    steps: int = 0
    tool_calls: int = 0
    files_read: list[str] = Field(default_factory=list)
    stop_reason: str = "answered"
    budget_exhausted: bool = False
    snapshot_id: str | None = None
    usage: dict | None = None
