"""Multi-agent loan review with a durable underwriter wait.

Intake and credit run first and are checkpointed. The workflow then waits for
``underwriter_approval``. After a restart, those two model calls are not run again.
The letter agent and the publish activity run only when a named approver accepts.
"""

from __future__ import annotations

from typing import Any

from agentplatform.durable_agents.runtime import (
    DurableAgent,
    DurableAgentApp,
    JsonHistoryStore,
    OrchestrationContext,
)

FILES: dict[str, dict[str, Any]] = {
    "L-2001": {"summary": "conventional file, DTI 41 percent, reserves 4 months", "score": 742},
    "L-2002": {"summary": "conventional file, DTI 52 percent, reserves 1 month", "score": 680},
}


def intake_respond(loan_id: str) -> dict[str, Any]:
    return {"loan_id": loan_id, "summary": FILES[loan_id]["summary"]}


def credit_respond(loan_id: str) -> dict[str, Any]:
    return {"loan_id": loan_id, "score": FILES[loan_id]["score"]}


def letter_respond(message: str) -> dict[str, Any]:
    return {"text": f"Decision letter based on {message}"}


def make_publisher(ledger: dict[str, dict[str, Any]]):
    """Publish is idempotent on its own, in case a handler is retried before it is checkpointed."""

    def publish_letter(payload: dict[str, Any]) -> dict[str, Any]:
        key = payload["idempotency_key"]
        existing = ledger.get(key)
        if existing is not None:
            return {**existing, "duplicate": True}
        ticket = {"ticket": f"LET-{payload['loan_id']}", "duplicate": False}
        ledger[key] = dict(ticket)
        return dict(ticket)

    return publish_letter


def loan_review_orchestration(ctx: OrchestrationContext):
    application = ctx.get_input()
    loan_id = application["loan_id"]
    intake = yield ctx.call_agent("intake", loan_id)
    credit = yield ctx.call_agent("credit", loan_id)
    approval = yield ctx.wait_for_event("underwriter_approval")
    approver = approval.get("approver") or ""
    if not approval.get("approved") or not approver:
        return {"status": "returned_to_processing", "loan_id": loan_id, "approver": approver}
    letter = yield ctx.call_agent("letter", f"{loan_id}|{intake['summary']}|score {credit['score']}")
    published = yield ctx.call_activity(
        "publish_letter",
        {"loan_id": loan_id, "idempotency_key": f"{loan_id}:letter", "text": letter["text"]},
    )
    return {
        "status": "issued",
        "loan_id": loan_id,
        "approver": approver,
        "letter": letter["text"],
        "ticket": published["ticket"],
        "duplicate": published["duplicate"],
    }


def build_loan_app(store: JsonHistoryStore) -> DurableAgentApp:
    app = DurableAgentApp(store)
    app.add_agent(DurableAgent("intake", intake_respond))
    app.add_agent(DurableAgent("credit", credit_respond))
    app.add_agent(DurableAgent("letter", letter_respond))
    app.add_activity("publish_letter", make_publisher({}))
    app.orchestrations["loan_review"] = loan_review_orchestration
    return app
