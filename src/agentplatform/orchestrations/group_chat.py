"""Group chat (maker-checker): specialists speak once each, then the underwriter (maker) and the
compliance reviewer (checker) alternate until the reviewer says APPROVED or the round cap is hit.

MAF: `GroupChatBuilder(participants=..., selection_func=... | orchestrator_agent=..., max_rounds=...,
termination_condition=..., output_from="all")`. Two speaker-selection modes are shown:
  * `selection="func"`: a deterministic Python `selection_func(GroupChatState) -> name` (no LLM cost);
  * `selection="agent"`: an LLM orchestrator agent that returns `AgentOrchestrationOutput` JSON
    (terminate / reason / next_speaker / final_message) every round.
Hitting `max_rounds` without approval is a safe stop: the verdict is forced to `refer`."""

from __future__ import annotations

import json
from typing import Any

from agent_framework import Agent, ChatResponse, Message, Workflow
from agent_framework.orchestrations import GroupChatBuilder, GroupChatState

from agentplatform.harness.tracing import span
from agentplatform.orchestrations.base import OrchestrationRun, responses, turns_of
from agentplatform.orchestrations.facts import LANES, expected_flags, gather_facts
from agentplatform.orchestrations.roles import CONDITIONS_RE, Roster, parse_list

MAX_ROUNDS = 9
ORCHESTRATOR_INSTRUCTIONS = (
    "You coordinate a mortgage conditions review. Let each analyst (income, credit, assets) speak once, then "
    "alternate underwriter and reviewer. Terminate when the reviewer says APPROVED. Reply with JSON only."
)


def approved(conversation: list[Message]) -> bool:
    return any(m.author_name == "reviewer" and (m.text or "").strip() == "APPROVED" for m in conversation)


def next_speaker(spoken: list[str | None]) -> str:
    """Shared policy: each lane once, then maker/checker alternation."""
    for lane in LANES:
        if lane not in spoken:
            return lane
    tail = [s for s in spoken if s in ("underwriter", "reviewer")]
    return "reviewer" if tail and tail[-1] == "underwriter" else "underwriter"


def select(state: GroupChatState) -> str:
    return next_speaker([m.author_name for m in state.conversation if m.role == "assistant"])


def orchestrator_script(msgs: list[Message], options: dict[str, Any]) -> ChatResponse:
    spoken = [m.author_name for m in msgs if m.role == "assistant" and m.author_name != "orchestrator"]
    done = approved(msgs)
    out = {
        "terminate": done,
        "reason": "reviewer approved" if done else "continue the review",
        "next_speaker": None if done else next_speaker(spoken),
        "final_message": None,
    }
    return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(out)])])


def build(roster: Roster, *, selection: str = "func", max_rounds: int = MAX_ROUNDS) -> Workflow:
    agents = roster.agents(*LANES, "underwriter", "reviewer")
    kwargs: dict[str, Any] = {"selection_func": select}
    if selection == "agent":
        kwargs = {
            "orchestrator_agent": Agent(
                client=roster.client(orchestrator_script),
                name="orchestrator",
                instructions=ORCHESTRATOR_INSTRUCTIONS,
            )
        }
    return GroupChatBuilder(
        name=f"orch-group-chat-{selection}",
        participants=list(agents.values()),
        termination_condition=approved,
        max_rounds=max_rounds,
        output_from="all",
        **kwargs,
    ).build()


async def run(
    loan_id: str, *, selection: str = "func", max_rounds: int = MAX_ROUNDS, faults: set[str] | None = None
) -> OrchestrationRun:
    facts = await gather_facts(loan_id)
    roster = Roster(facts, faults=faults)
    with span("orchestration.run", pattern="group_chat", loan=loan_id, selection=selection):
        result = await build(roster, selection=selection, max_rounds=max_rounds).run(
            f"Conditions review for loan {loan_id}."
        )
    turns = [
        t for t in turns_of(responses(result)) if t[0] not in ("orchestrator", "group_chat_orchestrator")
    ]
    ok = any(a == "reviewer" and t.strip() == "APPROVED" for a, t in turns)
    final = next((t for a, t in reversed(turns) if a == "underwriter"), "")
    if not ok:  # checker never signed off: safe stop, never a silent approval
        final = f"CONDITIONS: {', '.join(sorted(set(parse_list(CONDITIONS_RE, final)))) or 'none'}\nDECISION: refer"
    return OrchestrationRun(
        "group_chat" if selection == "func" else "group_chat_agent",
        loan_id,
        final,
        expected_flags(facts),
        roster.llm_calls,
        turns,
        [],
        "approved" if ok else "max_rounds_unapproved",
        {"rounds": sum(1 for a, _ in turns if a in (*LANES, "underwriter", "reviewer"))},
    )
