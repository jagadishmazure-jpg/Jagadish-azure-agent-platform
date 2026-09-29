"""Concurrent (fan-out / fan-in): the three specialists run in parallel; a deterministic aggregator
(no LLM) merges their FLAGS lines into the verdict.

MAF: `ConcurrentBuilder(participants=...).with_aggregator(callback)`. The callback receives
`list[AgentExecutorResponse]`; whatever it returns becomes the workflow output."""

from __future__ import annotations

from agent_framework import AgentExecutorResponse, Workflow
from agent_framework.orchestrations import ConcurrentBuilder

from agentplatform.harness.tracing import span
from agentplatform.orchestrations.base import OrchestrationRun
from agentplatform.orchestrations.facts import LANES, expected_flags, gather_facts
from agentplatform.orchestrations.roles import FLAGS_RE, Roster, parse_list, verdict


def aggregate(results: list[AgentExecutorResponse]) -> dict:
    """Fan-in: a lane with no FLAGS line is a missing lane -> refer, never a silent approve."""
    turns, flags, missing = [], [], []
    for r in results:
        text = r.agent_response.text
        turns.append((r.executor_id, text))
        if "FLAGS:" not in text:
            missing.append(r.executor_id)
        flags += parse_list(FLAGS_RE, text)
    final = verdict(flags)
    if missing:
        final = final.rsplit("DECISION:", 1)[0] + f"DECISION: refer\nMISSING_LANES: {', '.join(missing)}"
    return {"final": final, "turns": turns, "missing": missing}


def build(roster: Roster) -> Workflow:
    agents = roster.agents(*LANES)
    return (
        ConcurrentBuilder(name="orch-concurrent", participants=list(agents.values()))
        .with_aggregator(aggregate)
        .build()
    )


async def run(loan_id: str, *, faults: set[str] | None = None) -> OrchestrationRun:
    facts = await gather_facts(loan_id)
    roster = Roster(facts, faults=faults)
    with span("orchestration.run", pattern="concurrent", loan=loan_id):
        result = await build(roster).run(f"Conditions review for loan {loan_id}.")
    out = result.get_outputs()[-1]
    return OrchestrationRun(
        "concurrent",
        loan_id,
        out["final"],
        expected_flags(facts),
        roster.llm_calls,
        [*out["turns"], ("aggregator", out["final"])],
        [],
        "missing_lanes" if out["missing"] else "completed",
    )
