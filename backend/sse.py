"""Server-Sent Events plumbing for streamed agent activity.

The agent loop is a *synchronous* generator (it makes blocking model/tool
calls). To stream it without blocking the event loop, each ``next()`` is pumped
on a worker thread and the resulting :class:`AgentEvent` is emitted as an SSE
message whose ``event`` field is the event type and whose ``data`` is the
event JSON.
"""

from __future__ import annotations

from collections.abc import Iterator

import anyio
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from agent.models import AgentEvent, AgentEventType


async def _to_async(gen: Iterator[AgentEvent]):
    sentinel = object()

    def _next():
        try:
            return next(gen)
        except StopIteration:
            return sentinel

    while True:
        item = await anyio.to_thread.run_sync(_next)
        if item is sentinel:
            return
        yield item


def agent_event_stream(events: Iterator[AgentEvent]) -> EventSourceResponse:
    async def publisher():
        async for ev in _to_async(events):
            yield ServerSentEvent(event=ev.type.value, data=ev.model_dump_json())

    return EventSourceResponse(publisher())


def error_event_stream(message: str, code: str = "error") -> EventSourceResponse:
    """A one-shot SSE stream carrying an error, an answer, and a terminator, so the
    UI's normal event handling surfaces configuration/setup problems too."""

    events = [
        AgentEvent(type=AgentEventType.error, message=message, data={"code": code}),
        AgentEvent(type=AgentEventType.answer, message=message, data={"answer": message}),
        AgentEvent(type=AgentEventType.done, data={"stop_reason": code}),
    ]

    async def publisher():
        for ev in events:
            yield ServerSentEvent(event=ev.type.value, data=ev.model_dump_json())

    return EventSourceResponse(publisher())
