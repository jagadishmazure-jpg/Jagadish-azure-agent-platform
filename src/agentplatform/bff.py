"""Experience plane: BFF / orchestrator entry point (FastAPI, Container Apps behind APIM).

Identity: in Azure, APIM validates the Entra ID token and forwards `x-user`, `x-tenant-id`,
`x-groups` derived from claims (see infra/modules/apim.bicep policy). The BFF only trusts those headers
behind APIM (ingress is internal-only when privateLink/internal ingress is enabled). Offline, the
headers default to a demo principal so `curl` works.

    uvicorn agentplatform.bff:app --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from agentplatform.a2a.agents import underwriting_service
from agentplatform.a2a.registry import DIRECTORY
from agentplatform.config import get_settings
from agentplatform.harness.identity import Principal, child_traceparent, new_traceparent
from agentplatform.harness.killswitch import KILL_SWITCH
from agentplatform.harness.tracing import configure_tracing, span
from agentplatform.mortgage.models import UnderwriterDecision
from agentplatform.safety.content_safety import get_safety_gate
from agentplatform.single.hr_agent import ask_hr
from agentplatform.single.it_agent import ITDesk, run_it

ADMIN_GROUP = "platform-admins"
UNDERWRITER_GROUP = "underwriting"


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_tracing("experience-bff")
    yield


app = FastAPI(title="azure-agent-platform BFF", version="0.1.0", lifespan=lifespan)
IT_DESK = ITDesk()


def principal(
    x_user: str = Header("demo-user"),
    x_tenant_id: str | None = Header(None),
    x_groups: str = Header("employees,underwriting,loan-officers"),
) -> Principal:
    groups = frozenset(g.strip() for g in x_groups.split(",") if g.strip())
    return Principal(x_user, x_tenant_id or get_settings().tenant_id, groups, agent_id="experience-bff")


def traceparent(request: Request) -> str:
    tp = request.headers.get("traceparent")
    return child_traceparent(tp) if tp else new_traceparent()


def require(group: str):
    def dep(p: Principal = Depends(principal)) -> Principal:
        if group not in p.groups:
            raise HTTPException(403, f"requires group '{group}'")
        return p

    return dep


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    as_of: date | None = None
    approve: bool = False  # IT only: approver has confirmed the pending privileged action


class DecisionIn(BaseModel):
    approved: bool
    reason: str = ""
    remove_condition_ids: list[str] = Field(default_factory=list)


def _screen(text: str) -> None:
    verdict = get_safety_gate().check_inbound(text)
    if not verdict.allowed:
        raise HTTPException(400, {"error": "content_safety", "reasons": verdict.reasons})


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    s = get_settings()
    return {"ok": True, "mode": s.mode, "kill_switch": KILL_SWITCH.state()}


@app.post("/loans/{loan_id}/underwrite")
async def underwrite(loan_id: str, request: Request, p: Principal = Depends(require("loan-officers"))):
    tp = traceparent(request)
    with span("bff.underwrite", tenant=p.tenant_id, loan=loan_id):
        rec = await underwriting_service().start(loan_id, p, tp)
    return {**rec.__dict__, "traceparent": tp}


@app.get("/runs/{run_id}")
def get_run(run_id: str, p: Principal = Depends(principal)):
    rec = underwriting_service().runs.get(run_id)
    if rec is None or rec.tenant_id != p.tenant_id:
        raise HTTPException(404, "run not found")
    return rec.__dict__


@app.post("/runs/{run_id}/decision")
async def decide(run_id: str, body: DecisionIn, p: Principal = Depends(require(UNDERWRITER_GROUP))):
    svc = underwriting_service()
    rec = svc.runs.get(run_id)
    if rec is None or rec.tenant_id != p.tenant_id:
        raise HTTPException(404, "run not found")
    if rec.status != "awaiting_underwriter":
        raise HTTPException(409, f"run is {rec.status}")
    with span("bff.decision", tenant=p.tenant_id, run=run_id, approved=body.approved):
        rec = await svc.decide(
            run_id, UnderwriterDecision(body.approved, p.subject, body.reason, body.remove_condition_ids)
        )
    return rec.__dict__


@app.get("/directory")
def directory() -> list[dict]:
    return DIRECTORY.cards()


@app.post("/directory/{agent_id}/kill")
def kill(agent_id: str, p: Principal = Depends(require(ADMIN_GROUP))):
    try:
        DIRECTORY.get(agent_id)
    except KeyError as e:
        raise HTTPException(404, f"unknown agent {agent_id}") from e
    DIRECTORY.kill(agent_id)
    return {"agent": agent_id, "killed": True, "by": p.subject}


@app.post("/directory/{agent_id}/revive")
def revive(agent_id: str, p: Principal = Depends(require(ADMIN_GROUP))):
    DIRECTORY.revive(agent_id)
    return {"agent": agent_id, "killed": False, "by": p.subject}


@app.post("/chat/hr")
async def chat_hr(body: ChatIn, p: Principal = Depends(principal)):
    _screen(body.message)
    return (await ask_hr(body.message, p, body.as_of)).model_dump()


@app.post("/chat/it")
async def chat_it(body: ChatIn, p: Principal = Depends(principal)):
    _screen(body.message)
    approver = p.subject if (body.approve and "it-approvers" in p.groups) else None
    return await run_it(body.message, p, IT_DESK, approver=approver, approve=body.approve)
