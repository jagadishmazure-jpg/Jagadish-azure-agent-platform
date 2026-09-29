"""Handoff (decentralised routing): triage screens the file and hands control to only the lanes that
raise findings, each specialist hands to the next, the underwriter concludes.

MAF: `HandoffBuilder(participants=[Agent...])` + `.with_start_agent()` + `.add_handoff(src, [targets])` +
`.with_termination_condition(fn(conversation))`. The builder injects `handoff_to_<name>` tools; a model
routes by calling one. Without autonomous mode an agent that answers *without* handing off pauses the
workflow with a `HandoffAgentUserRequest` (human in the loop): here, triage asks for a missing loan id.
Participants must be real `Agent`s built with `require_per_service_call_history_persistence=True`."""

from __future__ import annotations

import re
from collections.abc import Callable

from agent_framework import Message, Workflow
from agent_framework.orchestrations import HandoffAgentUserRequest, HandoffBuilder

from agentplatform.harness.tracing import span
from agentplatform.orchestrations.base import OrchestrationRun, responses, turns_of
from agentplatform.orchestrations.facts import LANES, expected_flags, gather_facts
from agentplatform.orchestrations.hitl import drive
from agentplatform.orchestrations.roles import Roster

MAX_TURNS = 12


def concluded(conversation: list[Message]) -> bool:
    """Stop when the underwriter has issued a decision, or as a hard cap on agent turns."""
    if any(m.author_name == "underwriter" and "DECISION:" in (m.text or "") for m in conversation):
        return True
    return sum(1 for m in conversation if m.role == "assistant") >= MAX_TURNS


def build(roster: Roster) -> Workflow:
    a = roster.agents("triage", *LANES, "underwriter", handoff=True)
    b = (
        HandoffBuilder(name="orch-handoff", participants=list(a.values()))
        .with_start_agent(a["triage"])
        .add_handoff(a["triage"], [a[x] for x in (*LANES, "underwriter")])
        .with_termination_condition(concluded)
    )
    for lane in LANES:
        b = b.add_handoff(a[lane], [a[x] for x in (*LANES, "underwriter") if x != lane])
    return b.build()


def loan_id_answer(loan_id: str) -> Callable[[HandoffAgentUserRequest], object]:
    def respond(req: HandoffAgentUserRequest):
        return HandoffAgentUserRequest.create_response(f"Please review loan {loan_id}.")

    return respond


async def run(loan_id: str, *, prompt: str | None = None, faults: set[str] | None = None) -> OrchestrationRun:
    facts = await gather_facts(loan_id)
    roster = Roster(facts, faults=faults)
    wf = build(roster)
    hitl: list[str] = []
    text = prompt if prompt is not None else f"Conditions review for loan {loan_id}."
    with span("orchestration.run", pattern="handoff", loan=loan_id):
        last, results = await drive(
            lambda: wf.run(text), wf, loan_id_answer(loan_id), seen=hitl, max_pauses=2
        )
    outs = [r for res in results for r in responses(res)]
    turns = turns_of(outs)
    final = next((t for a, t in reversed(turns) if a == "underwriter"), "")
    hops = [(e.data.source, e.data.target) for res in results for e in res if e.type == "handoff_sent"]
    route = re.findall(r"ROUTE: ([a-z, ]*)", " ".join(t for a, t in turns if a == "triage"))
    return OrchestrationRun(
        "handoff",
        loan_id,
        final,
        expected_flags(facts),
        roster.llm_calls,
        turns,
        hitl,
        "completed" if final else ("awaiting_user" if last.get_request_info_events() else "no_decision"),
        {"handoffs": hops, "route": route},
    )
