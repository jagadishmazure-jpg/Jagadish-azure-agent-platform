"""Sequential (pipeline): income -> credit -> assets -> underwriter, then a human approves the underwriter.

MAF: `SequentialBuilder(participants=..., checkpoint_storage=...)` + `.with_request_info(agents=[...])`.
The request-info pause happens *after* the named agent answers; the human either approves
(`AgentRequestInfoResponse.approve()`) or sends feedback (`from_strings`) that makes the agent run again.
`restart=True` rebuilds the workflow from the latest checkpoint while paused (a process restart)."""

from __future__ import annotations

from agent_framework import AgentExecutorResponse, InMemoryCheckpointStorage, Workflow
from agent_framework.orchestrations import AgentRequestInfoResponse, SequentialBuilder

from agentplatform.harness.tracing import span
from agentplatform.orchestrations.base import OrchestrationRun, responses, turns_of
from agentplatform.orchestrations.facts import LANES, expected_flags, gather_facts
from agentplatform.orchestrations.hitl import Responder, drive
from agentplatform.orchestrations.roles import Roster


def approve_all(_: AgentExecutorResponse) -> AgentRequestInfoResponse:
    return AgentRequestInfoResponse.approve()


def build(roster: Roster, storage=None) -> Workflow:
    agents = roster.agents(*LANES, "underwriter")
    return (
        SequentialBuilder(
            name="orch-sequential", participants=list(agents.values()), checkpoint_storage=storage
        )
        .with_request_info(agents=["underwriter"])
        .build()
    )


async def run(
    loan_id: str, *, review: Responder = approve_all, restart: bool = False, faults: set[str] | None = None
) -> OrchestrationRun:
    facts = await gather_facts(loan_id)
    roster = Roster(facts, faults=faults)
    storage = InMemoryCheckpointStorage()
    wf = build(roster, storage)
    hitl: list[str] = []
    with span("orchestration.run", pattern="sequential", loan=loan_id):
        first = await wf.run(f"Conditions review for loan {loan_id}.")
        results = [first]
        if restart and first.get_request_info_events():
            wf = build(roster, storage)  # fresh graph, same storage: rehydrate and re-surface the request
            latest = await storage.get_latest(workflow_name=wf.name)
            results.append(await wf.run(checkpoint_id=latest.checkpoint_id, checkpoint_storage=storage))
        last, more = await drive(lambda: _const(results[-1]), wf, review, seen=hitl)
        results += more[1:]
    outs = [r for res in results for r in responses(res)]
    final = outs[-1].text if outs else ""
    turns = review_turns(results)
    turns += [t for t in turns_of(outs[-1:]) if t not in turns[-1:]]
    return OrchestrationRun(
        "sequential",
        loan_id,
        final,
        expected_flags(facts),
        roster.llm_calls,
        turns,
        hitl,
        "completed" if outs else "no_output",
        {"state": str(last.get_final_state()), "restarted": restart},
    )


def review_turns(results) -> list[tuple[str, str]]:
    """The conversation the human last reviewed (carried in the request-info payload)."""
    convs = [
        ev.data.full_conversation
        for res in results
        for ev in res.get_request_info_events()
        if isinstance(ev.data, AgentExecutorResponse)
    ]
    return [
        (m.author_name or "?", m.text)
        for m in (convs[-1] if convs else [])
        if m.role == "assistant" and m.text
    ]


async def _const(x):
    return x
