"""Offline checkpoint and resume for a multi-agent loan workflow.

This follows the Durable Task extension for Microsoft Agent Framework: each agent call is
checkpointed, a human wait releases the worker, and a later worker continues from the task
hub. Completed agent calls are not run again. The Learn article does not define a billing
API; a model call that does not run is not charged again here. See ASSUMPTIONS.

This is not the Durable Task Scheduler protocol and it does not import that SDK.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from agentplatform.ignite.data import APPLICATIONS
from agentplatform.ignite.money import debt_service_coverage, monthly_payment

AGENT_SPECS: dict[str, dict[str, Any]] = {
    "intake": {
        "name": "intake",
        "instructions": "Read the application and restate the facts. Do not decide and do not book.",
        "narrative": "Intake complete. The figures below are copied from the application record.",
        "input_tokens": 120,
        "output_tokens": 40,
    },
    "credit": {
        "name": "credit",
        "instructions": "Cite the supplied policy and the calculator output. Do not book the loan.",
        "narrative": "Credit memo drafted from the calculator and the supplied policy. Nothing was booked.",
        "input_tokens": 180,
        "output_tokens": 60,
    },
    "letter": {
        "name": "letter",
        "instructions": "Write the decision letter from the officer's recorded decision only.",
        "narrative": "Decision letter drafted from the officer's recorded decision.",
        "input_tokens": 200,
        "output_tokens": 80,
    },
}


class DurableError(RuntimeError):
    pass


class ModelClient:
    """Counts model invocations. Replay must not call ``complete`` for a finished agent."""

    def __init__(self) -> None:
        self.invocations: list[str] = []

    def complete(self, agent: str, instructions: str, prompt: str) -> tuple[str, int, int]:
        if not instructions.strip() or not prompt.strip():
            raise DurableError("agent call is missing instructions or a prompt")
        spec = AGENT_SPECS[agent]
        self.invocations.append(agent)
        return spec["narrative"], spec["input_tokens"], spec["output_tokens"]


class InquiryLog:
    """External bureau. A repeated request id does not create a second hard pull."""

    def __init__(self) -> None:
        self.attempts = 0
        self.hard_pulls = 0
        self._reports: dict[str, dict] = {}

    def pull(self, request_id: str, score: int) -> dict:
        self.attempts += 1
        existing = self._reports.get(request_id)
        if existing is not None:
            return dict(existing)
        report = {"request_id": request_id, "score": score}
        self._reports[request_id] = report
        self.hard_pulls += 1
        return dict(report)


class TaskHub:
    """In-memory stand-in for a Durable Task Scheduler task hub."""

    def __init__(self) -> None:
        self.instances: dict[str, dict[str, Any]] = {}

    def save(self, state: dict[str, Any]) -> None:
        self.instances[state["instance_id"]] = json.loads(json.dumps(state))

    def get(self, instance_id: str) -> dict[str, Any]:
        try:
            return self.instances[instance_id]
        except KeyError as exc:
            raise DurableError(f"unknown instance {instance_id}") from exc

    def export(self) -> str:
        return json.dumps(self.instances, sort_keys=True)

    @classmethod
    def loads(cls, raw: str) -> TaskHub:
        hub = cls()
        hub.instances = json.loads(raw)
        return hub


def charges(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [event["charge"] for event in state["history"] if event["charge"] is not None]


def billed_tokens(state: dict[str, Any]) -> int:
    return sum(item["input_tokens"] + item["output_tokens"] for item in charges(state))


class DurableWorkflowWorker:
    """One worker. A replacement worker gets a new model client and the same task hub."""

    def __init__(self, worker_id: str, hub: TaskHub, model: ModelClient, bureau: InquiryLog) -> None:
        self.worker_id = worker_id
        self.hub = hub
        self.model = model
        self.bureau = bureau
        self.compute_held = False

    def get_agent(self, name: str) -> dict[str, Any]:
        """Same role as ``context.GetAgent`` / ``app.get_agent`` in the Learn samples."""
        try:
            return AGENT_SPECS[name]
        except KeyError as exc:
            raise DurableError(f"agent {name} is not registered") from exc

    def start(self, application_id: str, *, stop_after: str | None = None) -> dict[str, Any]:
        if application_id not in APPLICATIONS:
            raise DurableError(f"unknown application {application_id}")
        if application_id not in self.hub.instances:
            self.hub.save(
                {
                    "instance_id": application_id,
                    "status": "running",
                    "application": dict(APPLICATIONS[application_id]),
                    "history": [],
                    "pending_request": None,
                }
            )
        return self.drive(application_id, stop_after=stop_after)

    def signal(
        self, instance_id: str, *, officer_id: str, approved: bool, reason: str = ""
    ) -> dict[str, Any]:
        state = self.hub.get(instance_id)
        if state["status"] == "completed":
            return state
        if state["status"] != "waiting":
            raise DurableError("not waiting for a credit officer")
        if not officer_id.strip():
            raise DurableError("a named credit officer is required")
        return self.drive(
            instance_id,
            approval={"officer_id": officer_id.strip(), "approved": approved, "reason": reason},
        )

    def drive(
        self,
        instance_id: str,
        *,
        approval: dict[str, Any] | None = None,
        stop_after: str | None = None,
    ) -> dict[str, Any]:
        self.compute_held = True
        state = self.hub.get(instance_id)
        done = {event["step"] for event in state["history"]}
        if "intake" not in done:
            self._agent_step(state, "intake", self._intake_prompt(state))
            if stop_after == "intake":
                return self._release(state, "running")
        if "credit" not in done:
            self._agent_step(state, "credit", self._credit_prompt(state))
            if stop_after == "credit":
                return self._release(state, "running")
        if "credit_officer" not in done:
            if approval is None:
                proposed = _step(state, "credit")["output"]
                state["pending_request"] = {
                    "kind": "credit_officer",
                    "application_id": state["instance_id"],
                    "proposed_decision": proposed["proposed_decision"],
                    "dscr": proposed["dscr"],
                    "conditions": list(proposed["conditions"]),
                    "prompt": "A named credit officer has to approve before booking.",
                }
                return self._release(state, "waiting")
            state["history"].append(
                {"step": "credit_officer", "kind": "approval", "output": dict(approval), "charge": None}
            )
            state["pending_request"] = None
            self.hub.save(state)
            if not approval["approved"]:
                self._activity(
                    state,
                    "adverse_notice",
                    {
                        "officer_id": approval["officer_id"],
                        "reason": approval["reason"],
                        "booked": False,
                    },
                )
                return self._release(state, "completed")
        if _approved(state) and "letter" not in done:
            self._agent_step(state, "letter", self._letter_prompt(state))
        if _approved(state) and "book" not in done:
            officer = _step(state, "credit_officer")["output"]["officer_id"]
            self._activity(
                state,
                "book",
                {
                    "idempotency_key": f"book-{state['instance_id']}",
                    "ticket": f"BK-{state['instance_id']}",
                    "approved_by": officer,
                    "booked": True,
                },
            )
        return self._release(state, "completed")

    def _release(self, state: dict[str, Any], status: str) -> dict[str, Any]:
        state["status"] = status
        self.hub.save(state)
        self.compute_held = False
        return self.hub.get(state["instance_id"])

    def _agent_step(self, state: dict[str, Any], name: str, prompt: str) -> None:
        spec = self.get_agent(name)
        facts = self._facts_for(state, name)
        narrative, input_tokens, output_tokens = self.model.complete(
            spec["name"], spec["instructions"], prompt
        )
        output = {"narrative": narrative, **facts}
        state["history"].append(
            {
                "step": name,
                "kind": "agent",
                "output": output,
                "charge": {
                    "agent": name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "worker_id": self.worker_id,
                },
            }
        )
        self.hub.save(state)

    def _activity(self, state: dict[str, Any], name: str, output: dict[str, Any]) -> None:
        state["history"].append({"step": name, "kind": "activity", "output": output, "charge": None})
        self.hub.save(state)

    def _facts_for(self, state: dict[str, Any], agent: str) -> dict[str, Any]:
        """Structured facts come from the application and the calculator, not the narrative."""
        application = state["application"]
        if agent == "intake":
            return {
                "application_id": application["application_id"],
                "borrower": application["borrower"],
                "principal": application["principal"],
            }
        if agent == "credit":
            report = self.bureau.pull(
                f"bureau-{application['application_id']}", int(application["bureau_score"])
            )
            return _credit_facts(application, report)
        credit = _step(state, "credit")["output"]
        officer = _step(state, "credit_officer")["output"]
        return {
            "decision": credit["proposed_decision"],
            "officer_id": officer["officer_id"],
            "dscr": credit["dscr"],
            "conditions": list(credit["conditions"]),
        }

    def _intake_prompt(self, state: dict[str, Any]) -> str:
        application = state["application"]
        return f"Application {application['application_id']} for {application['borrower']}."

    def _credit_prompt(self, state: dict[str, Any]) -> str:
        intake = _step(state, "intake")["output"]
        return f"Policy min DSCR {state['application']['min_dscr']}. Intake said: {intake['narrative']}"

    def _letter_prompt(self, state: dict[str, Any]) -> str:
        officer = _step(state, "credit_officer")["output"]
        credit = _step(state, "credit")["output"]
        return (
            f"Officer {officer['officer_id']} approved {credit['proposed_decision']} "
            f"at DSCR {credit['dscr']}."
        )


def _step(state: dict[str, Any], name: str) -> dict[str, Any]:
    for event in state["history"]:
        if event["step"] == name:
            return event
    raise DurableError(f"step {name} has not been checkpointed")


def _approved(state: dict[str, Any]) -> bool:
    if "credit_officer" not in {event["step"] for event in state["history"]}:
        return False
    return bool(_step(state, "credit_officer")["output"]["approved"])


def _credit_facts(application: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    payment = monthly_payment(
        Decimal(application["principal"]),
        Decimal(application["annual_rate"]),
        int(application["term_months"]),
    )
    coverage = debt_service_coverage(
        Decimal(application["monthly_noi"]),
        Decimal(application["existing_debt_service"]),
        payment,
    )
    minimum = Decimal(application["min_dscr"])
    proposed = "approve_with_conditions" if coverage >= minimum else "refer"
    conditions = (
        ["Insurance binder before booking (CREDIT-POLICY-SMB)"]
        if proposed == "approve_with_conditions"
        else [f"DSCR {coverage} is below {minimum} (CREDIT-POLICY-SMB)"]
    )
    return {
        "payment": str(payment),
        "dscr": str(coverage),
        "policy_id": "CREDIT-POLICY-SMB",
        "proposed_decision": proposed,
        "conditions": conditions,
        "bureau": report,
    }
