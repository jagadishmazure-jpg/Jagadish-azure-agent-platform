"""End-to-end offline demo: underwrite the three synthetic loans, approve at the HITL gate, print letters."""

from __future__ import annotations

import asyncio
import json
import logging

from agent_framework import InMemoryCheckpointStorage

from agentplatform.a2a.local import crm_lookup_via_a2a
from agentplatform.harness.identity import Principal, new_traceparent
from agentplatform.mortgage.models import UnderwriterDecision
from agentplatform.mortgage.service import UnderwritingService
from agentplatform.mortgage.workflow import Deps


async def main() -> None:
    logging.getLogger("agent_framework").setLevel(logging.ERROR)
    svc = UnderwritingService(deps=Deps(crm_lookup=crm_lookup_via_a2a), storage=InMemoryCheckpointStorage())
    uw = Principal("uw-demo", "contoso-mortgage", frozenset({"underwriting"}))
    for loan in ("L-1001", "L-1002", "L-1003"):
        rec = await svc.start(loan, uw, new_traceparent())
        review = rec.review or {}
        print(f"\n== {loan}: {rec.status} → recommendation={review.get('recommendation')}")
        for c in review.get("conditions", []):
            print(f"   {c['id']:<20} {c['timing']}  cites {', '.join(c['guideline_ids'])}")
        rec = await svc.decide(rec.run_id, UnderwriterDecision(True, "uw-demo", "demo approval"))
        letter = (rec.outcome or {}).get("letter") or {}
        print(f"   letter: {letter.get('decision')} — {letter.get('body', '')[:110]}")
        print("   LOS:", json.dumps((rec.outcome or {}).get("los_ticket")))


if __name__ == "__main__":
    asyncio.run(main())
