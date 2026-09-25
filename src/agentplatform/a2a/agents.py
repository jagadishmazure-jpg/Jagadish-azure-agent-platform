"""Skill handlers for the custom domain agents and the vendor stand-ins."""

from __future__ import annotations

from typing import Any

from agentplatform.a2a.server import CallContext, SkillHandler
from agentplatform.harness.identity import Principal
from agentplatform.mcp_servers._data import seed

_TASKS: dict[str, dict] = {}
_POSTINGS: dict[str, dict] = {}
FEES = {"L-1001": [{"fee": "appraisal", "amount": 650}, {"fee": "credit_report", "amount": 55}]}


def _idem(store: dict, key: str, value: dict) -> dict:
    if not key:
        raise ValueError("idempotency_key required for write skills")
    return store.setdefault(key, value)


async def crm_agent(skill: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    crm = seed()["crm"]
    if skill == "get_borrower_profile":
        rec = crm.get(args["borrower_id"])
        if rec is None:
            raise KeyError(args["borrower_id"])
        return {**rec, "tenant": ctx.tenant}
    if skill == "create_followup_task":
        return _idem(
            _TASKS,
            args.get("idempotency_key", ""),
            {
                "task_id": f"TASK-{len(_TASKS) + 1:04d}",
                "borrower_id": args["borrower_id"],
                "subject": args["subject"],
                "status": "queued",
            },
        )
    raise ValueError(skill)


async def erp_agent(skill: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    if skill == "get_fee_ledger":
        return {"loan_id": args["loan_id"], "fees": FEES.get(args["loan_id"], [])}
    if skill == "post_fee_invoice":
        return _idem(
            _POSTINGS,
            args.get("idempotency_key", ""),
            {
                "posting_id": f"AR-{len(_POSTINGS) + 1:05d}",
                "loan_id": args["loan_id"],
                "amount": args["amount"],
                "status": "queued",
            },
        )
    raise ValueError(skill)


async def dynamics_standin(skill: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    rec = seed()["crm"].get(args.get("borrower_id", ""), {})
    if skill == "get_contact":
        return {
            "contactid": f"dyn-{args['borrower_id']}",
            "preferredcontactmethodcode": rec.get("preferred_channel"),
            "standin": True,
        }
    if skill == "create_activity":
        return _idem(
            _TASKS,
            args.get("idempotency_key", ""),
            {"activityid": f"dyn-act-{len(_TASKS) + 1}", "status": "queued", "standin": True},
        )
    raise ValueError(skill)


async def salesforce_standin(skill: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    if skill == "get_lead":
        return {"Id": f"00Q-{args['borrower_id']}", "Status": "Working", "standin": True}
    if skill == "create_task":
        return _idem(
            _TASKS, args.get("idempotency_key", ""), {"Id": f"00T-{len(_TASKS) + 1}", "standin": True}
        )
    raise ValueError(skill)


async def sap_standin(skill: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    if skill == "get_billing_document":
        return {"VBELN": f"90{args['loan_id'][-4:]}", "items": FEES.get(args["loan_id"], []), "standin": True}
    if skill == "simulate_posting":
        return {"simulated": True, "balanced": True, "lines": 2, "standin": True}
    if skill == "commit_posting":
        return _idem(
            _POSTINGS,
            args.get("idempotency_key", ""),
            {"BELNR": f"51{len(_POSTINGS) + 1:08d}", "approved_by": args["approved_by"], "standin": True},
        )
    raise ValueError(skill)


_UW_SERVICE = None


def underwriting_service():
    global _UW_SERVICE
    if _UW_SERVICE is None:
        from agentplatform.a2a.local import crm_lookup_via_a2a
        from agentplatform.mortgage.service import UnderwritingService
        from agentplatform.mortgage.workflow import Deps

        _UW_SERVICE = UnderwritingService(deps=Deps(crm_lookup=crm_lookup_via_a2a))
    return _UW_SERVICE


async def underwriting_agent(skill: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    svc = underwriting_service()
    if skill == "submit_loan_file":
        groups = frozenset(args.get("groups") or ["underwriting"])
        rec = await svc.start(
            args["loan_id"], Principal(ctx.subject or ctx.caller, ctx.tenant, groups), ctx.traceparent
        )
    elif skill == "get_status":
        rec = svc.runs[args["run_id"]]
    else:
        raise ValueError(skill)
    return {"run_id": rec.run_id, "status": rec.status, "review": rec.review, "outcome": rec.outcome}


HANDLERS: dict[str, SkillHandler] = {
    "crm-agent": crm_agent,
    "erp-agent": erp_agent,
    "underwriting-agent": underwriting_agent,
    "dynamics-crm-standin": dynamics_standin,
    "salesforce-crm-standin": salesforce_standin,
    "sap-erp-standin": sap_standin,
}
