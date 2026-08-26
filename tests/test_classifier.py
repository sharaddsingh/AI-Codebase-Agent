"""Heuristic task classifier: deterministic intent mapping."""

from __future__ import annotations

import pytest

from agent.classifier import classify, strategy_for
from agent.models import TaskType


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Where is verify_token used?", TaskType.find_usages),
        ("Find all references to get_user", TaskType.find_usages),
        ("Why does the /me endpoint return 401?", TaskType.debug),
        ("This login flow is broken, what's the bug?", TaskType.debug),
        ("What files would change to add Google OAuth?", TaskType.change_impact),
        ("How do I implement rate limiting here?", TaskType.change_impact),
        ("How does authentication work?", TaskType.how_it_works),
        ("Explain the request flow", TaskType.how_it_works),
        ("Tell me about this repository", TaskType.general),
    ],
)
def test_classify(question: str, expected: TaskType) -> None:
    assert classify(question) == expected


def test_empty_question_is_general() -> None:
    assert classify("") == TaskType.general


def test_strategy_exists_for_every_task_type() -> None:
    for task_type in TaskType:
        assert strategy_for(task_type)
