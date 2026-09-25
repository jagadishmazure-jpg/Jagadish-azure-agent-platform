"""Render docs generated from code (single source of truth): docs/failure-table.md."""

from __future__ import annotations

import sys
from pathlib import Path

from agentplatform.harness.failure import FAILURE_TABLE

OUT = Path(__file__).resolve().parents[1] / "docs" / "failure-table.md"
EXITS = ["success", "retry", "compensate", "degrade", "escalate"]


def render() -> str:
    lines = [
        "# Five-exit failure table — mortgage underwriting graph",
        "",
        "Generated from `agentplatform.harness.failure.FAILURE_TABLE` by `scripts/render_docs.py`; the graph,",
        "the chaos tests in `tests/test_mortgage_workflow.py`, and this page read the same data.",
        "",
        "| Node | " + " | ".join(e.capitalize() for e in EXITS) + " |",
        "|---|" + "---|" * len(EXITS),
    ]
    for node, row in FAILURE_TABLE.items():
        cells = [row.get(e, "").replace("|", "\\|") for e in EXITS]
        lines.append(f"| **{node}** | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Chaos drills covered by tests: model outage (fallback → deterministic draft), search outage (known-policy",
        "cache, answer marked limited, evidence-dependent writes disabled), bureau outage (suspend, no decision),",
        "bureau timeout retried with the same request id (no double hard pull), LOS write failure (compensating",
        "`in_review` status), prompt injection in retrieved text (screened out), kill switch, HITL SLA expiry.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text() == text else 1)
    OUT.write_text(text)
