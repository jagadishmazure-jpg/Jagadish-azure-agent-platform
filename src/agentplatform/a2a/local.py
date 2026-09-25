"""In-process A2A mesh (offline/tests): every agent's real FastAPI/A2A app mounted behind an httpx
ASGI transport, so calls exercise the full protocol path without sockets. In Container Apps the same
client uses real URLs (A2A_<AGENT>_URL, routed through APIM)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import httpx

from agentplatform.a2a.agents import HANDLERS
from agentplatform.a2a.catalog import CATALOG, ORCHESTRATOR
from agentplatform.a2a.client import A2AClient
from agentplatform.a2a.server import create_a2a_app
from agentplatform.harness.identity import Principal

# ASGITransport does not run app lifespan; a2a logs a benign warning per request in that mode.
logging.getLogger("a2a.server.events.event_queue_v2").setLevel(logging.ERROR)


@lru_cache(maxsize=1)
def local_apps() -> dict[str, Any]:
    return {s.id: create_a2a_app(s, HANDLERS[s.id]) for s in CATALOG}


def local_client(caller: str) -> A2AClient:
    if os.environ.get("AAP_A2A_REMOTE") == "1":
        return A2AClient(caller)
    return A2AClient(caller, transports={k: httpx.ASGITransport(app=v) for k, v in local_apps().items()})


async def crm_lookup_via_a2a(borrower_id: str, principal: Principal, traceparent: str) -> dict[str, Any]:
    out = await local_client(ORCHESTRATOR).send(
        "crm-agent", "get_borrower_profile", {"borrower_id": borrower_id}, principal, traceparent
    )
    return out["output"]
