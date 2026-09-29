"""Drive a workflow through its human-in-the-loop pauses with a bounded number of answers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import Workflow, WorkflowRunResult

from agentplatform.harness.tracing import span

Responder = Callable[[Any], Any]


async def drive(
    first: Callable[[], Awaitable[WorkflowRunResult]],
    workflow: Workflow,
    respond: Responder,
    *,
    max_pauses: int = 5,
    seen: list[str] | None = None,
) -> tuple[WorkflowRunResult, list[WorkflowRunResult]]:
    """Run, then answer each pending request with `respond(request_data)` until idle (or max_pauses).

    Returns the last result and every intermediate one (outputs are spread across runs)."""
    seen = seen if seen is not None else []
    results = [await first()]
    while (pending := results[-1].get_request_info_events()) and len(seen) < max_pauses:
        answers = {}
        for ev in pending:
            seen.append(type(ev.data).__name__)
            with span("orchestration.hitl", request=type(ev.data).__name__):
                answers[ev.request_id] = respond(ev.data)
        results.append(await workflow.run(responses=answers))
    return results[-1], results
