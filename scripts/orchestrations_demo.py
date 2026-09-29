"""Offline demo of the five MAF orchestration patterns over the same loan-conditions review.

python scripts/orchestrations_demo.py                 # one transcript per pattern (L-1001)
python scripts/orchestrations_demo.py --loan L-1002 --pattern handoff
python scripts/orchestrations_demo.py --compare       # comparison + fault drills (markdown)
python scripts/orchestrations_demo.py --compare --write   # refresh docs/orchestration-patterns.md
python scripts/orchestrations_demo.py --compare --check   # exit 1 if that doc is stale (tests/CI)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from agentplatform.orchestrations import compare

DOC = Path(__file__).resolve().parents[1] / "docs" / "orchestration-patterns.md"


def quiet() -> None:
    for name in ("agent_framework", "agent_framework_orchestrations"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


async def show(loan: str, only: str | None) -> None:
    for name, fn in compare.PATTERNS.items():
        if only and not name.startswith(only):
            continue
        r = await fn(loan)
        print(
            f"\n== {name} · {loan} · {r.llm_calls} model calls · stop={r.stop_reason} · hitl={r.hitl_requests}"
        )
        for author, text in r.turns:
            print(f"   [{author}] {text.replace(chr(10), ' | ')[:150]}")
        print(f"   => conditions={r.conditions} decision={r.decision} matches rules={r.exact}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loan", default="L-1001")
    ap.add_argument("--pattern")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    quiet()
    if not a.compare:
        asyncio.run(show(a.loan, a.pattern))
        return 0
    block = compare.render(asyncio.run(compare.collect()))
    if a.write or a.check:
        doc = DOC.read_text(encoding="utf-8")
        fresh = compare.splice(doc, block)
        if a.check:
            if fresh != doc:
                print(f"{DOC.name} is stale: run scripts/orchestrations_demo.py --compare --write")
                return 1
            print(f"{DOC.name} is up to date")
            return 0
        DOC.write_text(fresh, encoding="utf-8")
        print(f"wrote {DOC}")
        return 0
    print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
