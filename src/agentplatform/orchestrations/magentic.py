"""Magentic (manager-led, dynamic plan): a manager builds a task ledger (facts + plan), then every round
writes a progress ledger (satisfied? looping? progress? next speaker + instruction). A human reviews the
plan before any agent runs. Stalls trigger a reset + replan; round/reset caps end the run.

MAF: `MagenticBuilder(participants=..., manager_agent=Agent, enable_plan_review=True, max_round_count,
max_stall_count, max_reset_count, checkpoint_storage)`. With `manager_agent` MAF wraps the agent in
`StandardMagenticManager`, which drives it with its own facts / plan / progress-ledger (JSON) / final-answer
prompts. Offline, `ManagerScript` answers those prompts deterministically; on Foundry a real model does.
Plan review pauses with `MagenticPlanReviewRequest`; answer `.approve()` or `.revise(feedback)`."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agent_framework import Agent, ChatResponse, InMemoryCheckpointStorage, Message, Workflow
from agent_framework.orchestrations import MagenticBuilder, MagenticPlanReviewRequest

from agentplatform.harness.tracing import span
from agentplatform.orchestrations.base import OrchestrationRun, responses, turns_of
from agentplatform.orchestrations.facts import LANES, expected_flags, gather_facts
from agentplatform.orchestrations.hitl import drive
from agentplatform.orchestrations.roles import Roster

MAX_ROUNDS = 10
MAX_STALLS = 1
MAX_RESETS = 2
MANAGER_INSTRUCTIONS = (
    "You manage a mortgage conditions review team. Plan the work across the analysts, then the underwriter; "
    "keep the progress ledger honest (mark no progress when an analyst returns no findings)."
)


class ManagerScript:
    """Deterministic stand-in for the manager model, keyed on StandardMagenticManager's prompts."""

    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.ledgers = 0

    def _given_up(self) -> set[str]:
        return {lane for lane, n in self.failures.items() if n >= 2}

    def plan(self) -> str:
        skip = self._given_up()
        steps = [f"{lane}: report findings" for lane in LANES if lane not in skip]
        tail = f" (skip {', '.join(sorted(skip))}: unavailable; underwriter must refer)" if skip else ""
        return "Plan:\n- " + "\n- ".join([*steps, "underwriter: conditions and decision" + tail])

    def ledger(self, msgs: list[Message]) -> str:
        self.ledgers += 1
        said = [(m.author_name, m.text or "") for m in msgs if m.role == "assistant"]
        last_author, last_text = said[-1] if said else (None, "")
        if last_author in LANES and "FLAGS:" not in last_text:
            self.failures[last_author] = self.failures.get(last_author, 0) + 1
        done = {a for a, t in said if a in LANES and "FLAGS:" in t}
        decided = any(a == "underwriter" and "DECISION:" in t for a, t in said)
        todo = [lane for lane in LANES if lane not in done and lane not in self._given_up()]
        nxt = todo[0] if todo else "underwriter"
        progress = not (last_author in LANES and "FLAGS:" not in last_text)
        item = lambda answer, reason="": {"reason": reason, "answer": answer}  # noqa: E731
        return json.dumps(
            {
                "is_request_satisfied": item(decided, "underwriter issued a decision" if decided else ""),
                "is_in_loop": item(False),
                "is_progress_being_made": item(
                    progress, "" if progress else f"{last_author} gave no findings"
                ),
                "next_speaker": item(nxt),
                "instruction_or_question": item(
                    f"{nxt}: report your findings for this loan."
                    if nxt != "underwriter"
                    else "underwriter: consolidate the FLAGS lines into conditions and a decision."
                    + (f"\nMISSING_LANES: {', '.join(sorted(self._given_up()))}" if self._given_up() else "")
                ),
            }
        )

    def __call__(self, msgs: list[Message], options: dict[str, Any]) -> ChatResponse:
        prompt = msgs[-1].text or ""
        if "progress ledger" in prompt.lower() or "is_request_satisfied" in prompt:
            text = self.ledger(msgs)
        elif "We have completed the task" in prompt or "final answer" in prompt.lower():
            text = next((m.text for m in reversed(msgs) if m.author_name == "underwriter"), "no decision")
        elif "Below I will present you a request" in prompt or "As a reminder" in prompt:
            text = "Facts: loan file, tri-merge credit, bank and income documents are available via the team."
        else:
            text = self.plan()
        return ChatResponse(messages=[Message(role="assistant", contents=[text])], model="mock-deterministic")


def approve_plan(req: MagenticPlanReviewRequest):
    return req.approve()


def revise_once(feedback: str) -> Callable[[MagenticPlanReviewRequest], Any]:
    state = {"n": 0}

    def respond(req: MagenticPlanReviewRequest):
        state["n"] += 1
        return req.revise(feedback) if state["n"] == 1 else req.approve()

    return respond


def build(roster: Roster, manager: ManagerScript, storage=None, *, max_rounds: int = MAX_ROUNDS) -> Workflow:
    agents = roster.agents(*LANES, "underwriter")
    manager_agent = Agent(client=roster.client(manager), name="manager", instructions=MANAGER_INSTRUCTIONS)
    return MagenticBuilder(
        name="orch-magentic",
        participants=list(agents.values()),
        manager_agent=manager_agent,
        enable_plan_review=True,
        max_round_count=max_rounds,
        max_stall_count=MAX_STALLS,
        max_reset_count=MAX_RESETS,
        checkpoint_storage=storage,
        output_from="all",
    ).build()


async def run(
    loan_id: str,
    *,
    review: Callable[[MagenticPlanReviewRequest], Any] = approve_plan,
    faults: set[str] | None = None,
    max_rounds: int = MAX_ROUNDS,
) -> OrchestrationRun:
    facts = await gather_facts(loan_id)
    roster = Roster(facts, faults=faults)
    manager = ManagerScript()
    wf = build(roster, manager, InMemoryCheckpointStorage(), max_rounds=max_rounds)
    hitl: list[str] = []
    with span("orchestration.run", pattern="magentic", loan=loan_id):
        _, results = await drive(
            lambda: wf.run(f"Conditions review for loan {loan_id}."), wf, review, seen=hitl, max_pauses=3
        )
    turns = turns_of([r for res in results for r in responses(res)])
    final = next((t for a, t in reversed(turns) if a == "underwriter" and "DECISION:" in t), "")
    events = [e.data.event_type.name for res in results for e in res if e.type == "magentic_orchestrator"]
    terminated = next((t for a, t in turns if "terminated due to" in t), None)
    return OrchestrationRun(
        "magentic",
        loan_id,
        final or "CONDITIONS: none\nDECISION: refer",
        expected_flags(facts),
        roster.llm_calls,
        turns,
        hitl,
        "limit_reached" if terminated else ("completed" if final else "no_decision"),
        {"ledgers": manager.ledgers, "events": sorted(set(events)), "terminated": terminated},
    )
