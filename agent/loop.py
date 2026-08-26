"""The bounded agentic loop.

This is the heart of the agent. Given a bound repository and a question, it:

1. **Classifies** the task (zero-token heuristic) and announces a **plan**.
2. Enters a **gather loop**: ask the model, and for every tool call it requests,
   execute it against the repository, feed the (untrusted-wrapped) result back,
   and repeat — until the model stops asking for tools or a **budget** trips.
3. On budget exhaustion, **forces a final answer** from evidence already gathered
   (one model call with tools disabled).
4. **Validates citations** in the answer against files actually inspected, so the
   agent cannot cite paths or line ranges it never looked at.

Every meaningful step is emitted as an :class:`AgentEvent`, which the backend
streams to the UI (planning → searching → reading → answering). The loop is a
plain generator; :meth:`AgentLoop.run_sync` drains it into an :class:`AgentResult`
for tests and non-streaming callers.

Security posture (enforced here, not merely requested of the model):
- Tools are read-only and repo-scoped; the repo is bound by the loop, never a
  tool argument, so the model cannot redirect a tool at another path.
- Tool output is wrapped in an explicit untrusted-data envelope before it re-enters
  the model context.
- Budgets bound tool calls, wall-clock time, files read, context bytes, and steps.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from code_intelligence.models import Citation
from code_intelligence.repository import RepositoryInterface

from .budget import Budget, BudgetTracker
from .classifier import classify, strategy_for
from .model_adapter import ModelAdapter, ModelCallError, ModelResponse
from .models import AgentEvent, AgentEventType, AgentResult, TaskType
from .prompts import (
    CLEAN_FINALIZE_INSTRUCTION,
    FORCE_ANSWER_NUDGE,
    SYSTEM_PROMPT,
    build_user_prompt,
    wrap_tool_output,
)
from .tools_spec import TOOL_SCHEMAS, execute_tool

# path:line  or  path:start-end  (en-dash tolerated). Validated against evidence.
_CITATION_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./\-]*\.[A-Za-z0-9_./\-]+|[A-Za-z0-9_./\-]+/[A-Za-z0-9_./\-]+):(\d+)(?:\s*[-–]\s*(\d+))?")


class AgentLoop:
    def __init__(
        self,
        adapter: ModelAdapter,
        *,
        budget: Budget | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.adapter = adapter
        self.budget = budget or Budget()
        self.temperature = temperature

    # -- public API -------------------------------------------------------
    def run(self, repo: RepositoryInterface, question: str) -> Iterator[AgentEvent]:
        """Run the investigation, yielding events. The terminal ``answer`` event's
        ``data`` carries the full :class:`AgentResult` as a dict."""

        try:
            yield from self._run_inner(repo, question)
        except ModelCallError as exc:
            result = AgentResult(
                answer=(
                    "The model call failed, so the investigation could not complete. "
                    f"Details: {exc}"
                ),
                task_type=TaskType.general,
                stop_reason="model_error",
            )
            yield AgentEvent(type=AgentEventType.error, message=str(exc))
            yield AgentEvent(
                type=AgentEventType.answer, message=result.answer, data=result.model_dump(mode="json")
            )
            yield AgentEvent(type=AgentEventType.done, data={"stop_reason": result.stop_reason})

    def run_sync(self, repo: RepositoryInterface, question: str) -> AgentResult:
        """Drain :meth:`run` and return the final result (for tests / non-streaming)."""

        result: AgentResult | None = None
        for event in self.run(repo, question):
            if event.type is AgentEventType.answer and event.data is not None:
                result = AgentResult.model_validate(event.data)
        assert result is not None, "run() must always emit an answer event"
        return result

    # -- internals --------------------------------------------------------
    def _run_inner(self, repo: RepositoryInterface, question: str) -> Iterator[AgentEvent]:
        snapshot = repo.get_snapshot()
        task_type = classify(question)
        tracker = BudgetTracker(self.budget)

        yield AgentEvent(
            type=AgentEventType.classified,
            message=f"Task classified as '{task_type.value}'.",
            data={"task_type": task_type.value, "snapshot_id": snapshot.id},
        )
        yield AgentEvent(
            type=AgentEventType.plan,
            message=strategy_for(task_type),
            data={"strategy": strategy_for(task_type)},
        )

        user_prompt = build_user_prompt(question, task_type, repo.display_name or repo.id)
        messages: list[dict] = [{"role": "user", "content": user_prompt}]

        # Evidence accumulated across the run, used for citation validation.
        known_paths: set[str] = set()
        known_total_lines: dict[str, int] = {}
        last_usage: dict | None = None

        # Retry breaker (source-agnostic): remember which exact (tool, args) calls
        # have already failed so an identical call is skipped rather than retried
        # until the budget is exhausted. Fixes the rate-limit / error retry storm.
        failure_counts: dict[str, int] = {}
        last_error: dict[str, str | None] = {}

        answer_text: str | None = None
        forced = False

        while True:
            reason = tracker.exceeded()
            if reason is not None:
                forced = True
                yield AgentEvent(
                    type=AgentEventType.budget,
                    message=f"Investigation budget reached ({reason}); composing answer.",
                    data={"reason": reason, **tracker.snapshot()},
                )
                break

            tracker.start_step()
            step = tracker.steps
            yield AgentEvent(
                type=AgentEventType.status,
                message="Analyzing the repository…",
                step=step,
                data=tracker.snapshot(),
            )

            resp = self.adapter.complete(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_SCHEMAS,
                temperature=self.temperature,
            )
            last_usage = resp.usage or last_usage

            if not resp.tool_calls:
                answer_text = resp.text or ""
                break

            # Record the assistant's tool-call turn in the internal schema.
            messages.append(_assistant_tool_call_message(resp))

            for tc in resp.tool_calls:
                # Each tool_call in the assistant message MUST get a tool response,
                # even when a budget forbids executing it (protocol requirement).
                if tracker.tool_calls_left() <= 0:
                    messages.append(_tool_result_message(tc.id, _budget_stub("tool_calls")))
                    continue

                is_read = tc.name == "read_file"
                if is_read and not tracker.can_read_more_files():
                    tracker.register_tool_call()
                    messages.append(_tool_result_message(tc.id, _budget_stub("files")))
                    yield AgentEvent(
                        type=AgentEventType.tool_result,
                        message="File-read budget reached; skipping read.",
                        step=step,
                        data={"tool": tc.name, "ok": False, "reason": "file_budget"},
                    )
                    continue

                # Retry breaker: if this exact call already failed once, skip it
                # instead of re-running it. Still counts against the tool-call
                # budget so the loop cannot spin, and tells the model to change
                # approach or finalize.
                call_key = _call_key(tc.name, tc.arguments)
                if failure_counts.get(call_key, 0) >= 1:
                    tracker.register_tool_call()
                    messages.append(
                        _tool_result_message(tc.id, _repeat_stub(tc.name, last_error.get(call_key)))
                    )
                    yield AgentEvent(
                        type=AgentEventType.tool_result,
                        message=f"Skipping repeated failing call to {tc.name}; it already failed once.",
                        step=step,
                        data={"tool": tc.name, "ok": False, "error": "repeated_failure"},
                    )
                    continue

                yield AgentEvent(
                    type=AgentEventType.tool_call,
                    message=f"{tc.name}({_short_args(tc.arguments)})",
                    step=step,
                    data={"tool": tc.name, "arguments": tc.arguments},
                )

                tracker.register_tool_call()
                execu = execute_tool(repo, tc.name, tc.arguments)
                if not execu.ok:
                    failure_counts[call_key] = failure_counts.get(call_key, 0) + 1
                    last_error[call_key] = execu.error

                # Fold in evidence for budgets + citation validation.
                for path in execu.files:
                    known_paths.add(path)
                for path, _start, _end in execu.ranges:
                    tracker.register_file(path)
                payload = execu.payload
                if tc.name == "read_file" and execu.ok:
                    known_total_lines[str(payload.get("path"))] = int(payload.get("total_lines", 0))
                if tc.name == "get_file_metadata" and execu.ok:
                    p = str(payload.get("path"))
                    known_paths.add(p)
                    known_total_lines[p] = int(payload.get("line_count", 0))

                wrapped = wrap_tool_output(tc.name, tc.arguments, payload)
                tracker.add_context(len(wrapped.encode("utf-8", "ignore")))
                messages.append(_tool_result_message(tc.id, wrapped))

                yield AgentEvent(
                    type=AgentEventType.tool_result,
                    message=execu.summary,
                    step=step,
                    data={"tool": tc.name, "ok": execu.ok, "error": execu.error},
                )

        if answer_text is None:
            # Budget tripped before the model volunteered an answer. Force one,
            # robustly, so the evidence already gathered is never wasted.
            answer_text, forced_usage = self._forced_answer(messages, user_prompt, tracker)
            last_usage = forced_usage or last_usage

        if not answer_text.strip():
            # Natural stop (model quit calling tools) but it returned no text.
            answer_text = (
                "I could not produce an answer from the available evidence. "
                "Try narrowing the question or pointing me at a specific file or symbol."
            )

        citations = _extract_citations(answer_text, known_paths, known_total_lines, snapshot.id)
        stop_reason = "budget_exhausted" if forced else "answered"

        result = AgentResult(
            answer=answer_text,
            citations=citations,
            task_type=task_type,
            steps=tracker.steps,
            tool_calls=tracker.tool_calls,
            files_read=sorted(tracker._files_read),
            stop_reason=stop_reason,
            budget_exhausted=forced,
            snapshot_id=snapshot.id,
            usage=last_usage,
        )

        yield AgentEvent(
            type=AgentEventType.answer, message=answer_text, data=result.model_dump(mode="json")
        )
        yield AgentEvent(
            type=AgentEventType.done,
            data={"stop_reason": stop_reason, **tracker.snapshot()},
        )

    def _forced_answer(
        self,
        messages: list[dict],
        user_prompt: str,
        tracker: BudgetTracker,
    ) -> tuple[str, dict | None]:
        """Compose a final answer after the budget tripped — robustly.

        The naive approach (ask once over the full transcript with tools
        disabled) can come back empty against a real model: after a long run of
        ``tool_use``/``tool_result`` blocks the model is primed to keep calling
        tools and, with none available, sometimes emits no text at all. That
        would throw away everything already read. So we escalate:

        1. Ask on the full transcript (tools disabled) — the normal case.
        2. If that is empty, retry on a **clean** context: the original question
           plus a plain-text digest of the gathered evidence, with no dangling
           tool-use blocks to suppress the completion.
        3. If still empty, return a deterministic summary of what was inspected
           so the user gets a useful pointer instead of a dead end.
        """

        usage: dict | None = None

        # Attempt 1 — full transcript + nudge, tools disabled.
        convo = messages + [{"role": "user", "content": FORCE_ANSWER_NUDGE}]
        tracker.start_step()
        resp = self.adapter.complete(
            system=SYSTEM_PROMPT, messages=convo, tools=None, temperature=self.temperature
        )
        usage = resp.usage or usage
        text = (resp.text or "").strip()
        if text:
            return text, usage

        # Attempt 2 — clean context (no tool-use blocks), evidence inlined as data.
        digest = _evidence_digest(messages)
        if digest:
            clean = [
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\n{CLEAN_FINALIZE_INSTRUCTION}\n\n"
                        f"=== EVIDENCE GATHERED (untrusted repository data) ===\n{digest}"
                    ),
                }
            ]
            tracker.start_step()
            resp = self.adapter.complete(
                system=SYSTEM_PROMPT, messages=clean, tools=None, temperature=self.temperature
            )
            usage = resp.usage or usage
            text = (resp.text or "").strip()
            if text:
                return text, usage

        # Attempt 3 — deterministic, evidence-grounded fallback (never a dead end).
        inspected = sorted(tracker._files_read)
        if inspected:
            listed = ", ".join(inspected)
            return (
                "I ran out of investigation budget before I could compose a full "
                f"answer. I did inspect these files: {listed}. Ask again about one "
                "of them specifically, or narrow the question, and I can go deeper."
            ), usage
        return (
            "I could not produce an answer from the available evidence. Try "
            "narrowing the question or pointing me at a specific file or symbol."
        ), usage


# -- message construction (internal OpenAI-style schema; adapters translate) --
def _assistant_tool_call_message(resp: ModelResponse) -> dict:
    return {
        "role": "assistant",
        "content": resp.text or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in resp.tool_calls
        ],
    }


def _tool_result_message(tool_call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _budget_stub(kind: str) -> str:
    msgs = {
        "tool_calls": "Tool-call budget exhausted. Do not request more tools; answer now.",
        "files": "File-read budget exhausted. Do not read more files; answer from what you have.",
    }
    return wrap_tool_output("_budget", {"kind": kind}, {"error": "budget", "message": msgs[kind]})


def _call_key(name: str, args: dict) -> str:
    """Canonical identity for a tool call, stable across argument key ordering."""
    try:
        return name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return name + ":" + str(args)


def _repeat_stub(name: str, code: str | None) -> str:
    detail = f" (it failed with '{code}')" if code else ""
    msg = (
        f"The tool '{name}' was already called with these exact arguments and "
        f"failed{detail}; it was not retried. Do not repeat this call — try a "
        "different tool or different arguments, or answer from the evidence you "
        "already have."
    )
    return wrap_tool_output(
        "_repeat", {"tool": name}, {"error": "repeated_failure", "message": msg}
    )


def _evidence_digest(messages: list[dict]) -> str:
    """Concatenate the tool results from the transcript into one plain-text block.

    Each result is already wrapped in an ``<tool_output …>`` untrusted-data
    envelope, so the injection defense is preserved when this is inlined into the
    clean-context finalization prompt.
    """

    parts = [
        str(m.get("content") or "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]
    return "\n\n".join(p for p in parts if p.strip())


def _short_args(args: dict) -> str:
    try:
        s = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(args)
    return s if len(s) <= 120 else s[:117] + "…"


# -- citation validation --------------------------------------------------
def _extract_citations(
    text: str,
    known_paths: set[str],
    known_total_lines: dict[str, int],
    snapshot_id: str,
) -> list[Citation]:
    """Pull ``path:line`` / ``path:start-end`` references out of the answer and keep
    only those whose path was actually inspected (and whose lines are plausible)."""

    seen: set[tuple[str, int, int]] = set()
    citations: list[Citation] = []
    for match in _CITATION_RE.finditer(text):
        path = match.group(1)
        if path not in known_paths:
            continue  # never inspected → not a valid citation
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        if end < start:
            start, end = end, start
        total = known_total_lines.get(path)
        if total:
            if start > total:
                continue  # hallucinated line number beyond the file
            end = min(end, total)
        key = (path, start, end)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(path=path, start_line=start, end_line=end, snapshot_id=snapshot_id)
        )
    return citations
