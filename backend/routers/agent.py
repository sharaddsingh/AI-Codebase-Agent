"""The agent chat endpoint: streams investigation activity over SSE."""

from __future__ import annotations

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from agent.model_adapter import ModelConfigError
from code_intelligence.errors import RepositoryNotFoundError

from ..deps import get_agent_loop, get_registry
from ..schemas import AgentChatRequest
from ..sse import agent_event_stream, error_event_stream

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat")
def agent_chat(body: AgentChatRequest) -> EventSourceResponse:
    """Run the bounded agent loop against a registered repository, streaming
    planning / searching / reading / answering events as they happen.

    Setup problems (unknown repo, unconfigured model) are returned as a one-shot
    SSE error stream so the chat UI surfaces them inline rather than as a broken
    fetch."""

    try:
        repo = get_registry().get(body.repo_id)
    except RepositoryNotFoundError as exc:
        return error_event_stream(exc.message, code="repo_not_found")
    try:
        loop = get_agent_loop()
    except ModelConfigError as exc:
        return error_event_stream(str(exc), code="model_not_configured")

    return agent_event_stream(loop.run(repo, body.question))
