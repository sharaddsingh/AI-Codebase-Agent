"""Heuristic task classification.

A tiny, deterministic, zero-token classifier that maps a natural-language
question onto a :class:`TaskType`. It runs before the model loop so the agent
can announce a strategy immediately (good for the streamed "planning" step) and
so the first user prompt carries task-specific guidance. It is intentionally
simple; a later phase can replace it with a model-based classifier behind the
same function signature.
"""

from __future__ import annotations

import re

from .models import TaskType

_PATTERNS: list[tuple[TaskType, re.Pattern[str]]] = [
    (
        TaskType.find_usages,
        re.compile(
            r"\b(where\s+is|where\s+are|used|usage|usages|call(?:ed|s|\s*sites?)?|"
            r"reference[sd]?|invoked|imported)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TaskType.debug,
        re.compile(
            r"\b(why|bug|fail(?:s|ing|ed)?|error|broken|crash|exception|"
            r"return(?:s|ing)?\s+\d{3}|\b\d{3}\b|throw|traceback|stack\s*trace|"
            r"not\s+work)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TaskType.change_impact,
        re.compile(
            r"\b(add|implement|introduce|support|integrate|refactor|rename|migrate|"
            r"what\s+(?:files|would\s+change)|change\s+to|how\s+(?:do|would)\s+i\s+add)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TaskType.how_it_works,
        re.compile(
            r"\b(how\s+does|how\s+is|how\s+are|explain|walk\s+me\s+through|"
            r"what\s+happens|architecture|flow|work[s]?)\b",
            re.IGNORECASE,
        ),
    ),
]


def classify(question: str) -> TaskType:
    q = question or ""
    # Priority order: usages and debugging are the most specific intents.
    for task_type, pattern in _PATTERNS:
        if pattern.search(q):
            return task_type
    return TaskType.general


def strategy_for(task_type: TaskType) -> str:
    """A short, human-readable strategy line for the streamed 'plan' event."""

    return {
        TaskType.how_it_works: "Locate entry points and implementing modules, then trace the flow.",
        TaskType.find_usages: "Search for the symbol, then confirm each call site by reading it.",
        TaskType.debug: "Find where the result/error is produced and enumerate its trigger conditions.",
        TaskType.change_impact: "Map the current implementation, then list files to add or modify.",
        TaskType.general: "Locate relevant files, read what matters, and cite the evidence.",
    }[task_type]
