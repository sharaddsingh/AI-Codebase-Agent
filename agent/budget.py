"""Agent budgets.

Every run is bounded on four axes the PRD calls out — tool calls, elapsed time,
files read, and accumulated context size — plus a hard cap on model round-trips.
The tracker is the single source of truth the loop consults before each step and
before each tool execution; when a limit trips, the loop stops gathering and
forces a final answer from whatever evidence it already has.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Budget:
    max_tool_calls: int = 12
    max_seconds: float = 90.0
    max_files_read: int = 20
    max_context_bytes: int = 200_000
    max_steps: int = 16  # model round-trips (each may issue multiple tool calls)


@dataclass
class BudgetTracker:
    budget: Budget
    started_at: float = field(default_factory=time.monotonic)
    tool_calls: int = 0
    steps: int = 0
    context_bytes: int = 0
    _files_read: set[str] = field(default_factory=set)

    # ---- queries --------------------------------------------------------
    @property
    def files_read(self) -> int:
        return len(self._files_read)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def time_left(self) -> float:
        return max(0.0, self.budget.max_seconds - self.elapsed)

    def tool_calls_left(self) -> int:
        return max(0, self.budget.max_tool_calls - self.tool_calls)

    def can_read_more_files(self) -> bool:
        return self.files_read < self.budget.max_files_read

    def exceeded(self) -> str | None:
        """Return a reason string if any *stop* limit is reached, else None."""
        if self.elapsed >= self.budget.max_seconds:
            return "time"
        if self.steps >= self.budget.max_steps:
            return "steps"
        if self.tool_calls >= self.budget.max_tool_calls:
            return "tool_calls"
        if self.context_bytes >= self.budget.max_context_bytes:
            return "context"
        return None

    # ---- mutations ------------------------------------------------------
    def start_step(self) -> None:
        self.steps += 1

    def register_tool_call(self) -> None:
        self.tool_calls += 1

    def register_file(self, path: str) -> None:
        self._files_read.add(path)

    def add_context(self, nbytes: int) -> None:
        self.context_bytes += max(0, nbytes)

    def snapshot(self) -> dict[str, float | int]:
        return {
            "tool_calls": self.tool_calls,
            "tool_calls_left": self.tool_calls_left(),
            "steps": self.steps,
            "files_read": self.files_read,
            "context_bytes": self.context_bytes,
            "elapsed_s": round(self.elapsed, 2),
        }
