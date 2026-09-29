"""Run every orchestration over the three synthetic loans (and a fault matrix) and render the comparison
that `docs/orchestration-patterns.md` embeds. Offline numbers come from the deterministic mock model, so
they measure orchestration overhead and control flow, not model quality; tokens and latency are not
reported because the mock has neither."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agentplatform.orchestrations import concurrent, group_chat, handoff, magentic, sequential
from agentplatform.orchestrations.base import OrchestrationRun

LOANS = ("L-1001", "L-1002", "L-1003")
SPEAKERS = {"triage", "income", "credit", "assets", "underwriter", "reviewer"}
START, END = "<!-- comparison:start -->", "<!-- comparison:end -->"

PATTERNS: dict[str, Callable[..., Awaitable[OrchestrationRun]]] = {
    "sequential": sequential.run,
    "concurrent": concurrent.run,
    "handoff": handoff.run,
    "group_chat (selection_func)": lambda loan, **kw: group_chat.run(loan, selection="func", **kw),
    "group_chat (orchestrator_agent)": lambda loan, **kw: group_chat.run(loan, selection="agent", **kw),
    "magentic": magentic.run,
}
DOWN = "assets analyst down (L-1001)"
DRILLS: list[tuple[str, str, Callable[[], Awaitable[OrchestrationRun]]]] = [
    ("sequential", DOWN, lambda: sequential.run("L-1001", faults={"assets_down"})),
    ("concurrent", DOWN, lambda: concurrent.run("L-1001", faults={"assets_down"})),
    ("handoff", DOWN, lambda: handoff.run("L-1001", faults={"assets_down"})),
    ("group_chat (selection_func)", DOWN, lambda: group_chat.run("L-1001", faults={"assets_down"})),
    ("magentic", DOWN, lambda: magentic.run("L-1001", faults={"assets_down"})),
    (
        "group_chat (selection_func)",
        "reviewer never approves (L-1001)",
        lambda: group_chat.run("L-1001", faults={"looping_reviewer"}),
    ),
    ("handoff", "request has no loan id (L-1002)", lambda: handoff.run("L-1002", prompt="Review this file.")),
    ("magentic", "max_round_count=2 (L-1001)", lambda: magentic.run("L-1001", max_rounds=2)),
    ("sequential", "process restart while paused (L-1003)", lambda: sequential.run("L-1003", restart=True)),
]


def speaker_turns(r: OrchestrationRun) -> int:
    return sum(1 for a, _ in r.turns if a in SPEAKERS)


async def collect() -> dict[str, Any]:
    logging.getLogger("agent_framework").setLevel(logging.ERROR)
    logging.getLogger("agent_framework_orchestrations").setLevel(logging.ERROR)
    table = []
    for name, fn in PATTERNS.items():
        runs = [await fn(loan) for loan in LOANS]
        table.append(
            {
                "pattern": name,
                "exact": sum(r.exact for r in runs),
                "recall": sum(r.recall for r in runs) / len(runs),
                "llm_calls": sum(r.llm_calls for r in runs) / len(runs),
                "turns": sum(speaker_turns(r) for r in runs) / len(runs),
                "hitl": sum(len(r.hitl_requests) for r in runs) / len(runs),
                "decisions": [r.decision for r in runs],
            }
        )
    faults = []
    for name, drill, fn in DRILLS:
        faults.append({"pattern": name, "drill": drill, **_fault(await fn())})
    return {"table": table, "faults": faults}


def _fault(r: OrchestrationRun) -> dict[str, Any]:
    return {
        "decision": r.decision or "none",
        "stop": r.stop_reason,
        "llm_calls": r.llm_calls,
        "hitl": len(r.hitl_requests),
        "exact": r.exact,
    }


def render(data: dict[str, Any]) -> str:
    n = len(LOANS)
    lines = [
        START,
        f"| Pattern | Exact conditions + decision ({n} loans) | Flag recall | LLM calls / loan | "
        "Agent turns / loan | HITL pauses / loan | Decisions (L-1001, L-1002, L-1003) |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in data["table"]:
        lines.append(
            f"| {row['pattern']} | {row['exact']}/{n} | {row['recall']:.2f} | {row['llm_calls']:.1f} | "
            f"{row['turns']:.1f} | {row['hitl']:.1f} | {', '.join(d or 'none' for d in row['decisions'])} |"
        )
    lines += [
        "",
        "| Pattern | Drill | Decision | Stop reason | LLM calls | HITL pauses |",
        "|---|---|---|---|---|---|",
    ]
    for f in data["faults"]:
        lines.append(
            f"| {f['pattern']} | {f['drill']} | {f['decision']} | {f['stop']} | {f['llm_calls']} | {f['hitl']} |"
        )
    lines.append(END)
    return "\n".join(lines)


def splice(doc: str, block: str) -> str:
    head, rest = doc.split(START, 1)
    _, tail = rest.split(END, 1)
    return head + block + tail
