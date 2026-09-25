"""Workflow messages. Kept JSON-native (dicts/lists inside dataclasses) so MAF checkpoints are
portable to Cosmos DB and only these three types need allow-listing for checkpoint decoding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CHECKPOINT_TYPES = [
    "agentplatform.mortgage.models:LoanRequest",
    "agentplatform.mortgage.models:UWState",
    "agentplatform.mortgage.models:UnderwriterReview",
    "agentplatform.mortgage.models:UnderwriterDecision",
]


@dataclass
class LoanRequest:
    loan_id: str
    principal: dict[str, Any]  # {"subject","tenant_id","groups":[...]}
    traceparent: str
    run_id: str


@dataclass
class UWState:
    loan_id: str
    run_id: str
    principal: dict[str, Any]
    traceparent: str
    loan: dict[str, Any] = field(default_factory=dict)
    crm: dict[str, Any] = field(default_factory=dict)
    documents: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # doc_id -> {doc_type, model_id, fields}
    income: dict[str, Any] = field(default_factory=dict)
    assets: dict[str, Any] = field(default_factory=dict)
    credit: dict[str, Any] = field(default_factory=dict)
    capacity: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)  # packed context: items, dropped, limited
    graph_paths: list[list[str]] = field(default_factory=list)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    critic: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    narratives: dict[str, str] = field(default_factory=dict)
    exits: dict[str, str] = field(default_factory=dict)  # node -> five-exit outcome
    issues: list[str] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    lane: str = ""  # which fan-out branch produced this copy

    def exit(self, node: str, outcome: str, reason: str = "") -> None:
        self.exits[node] = str(outcome)
        if reason:
            self.issues.append(f"{node}: {reason}")


@dataclass
class UnderwriterReview:
    """HITL request: evidence pack + proposed payload, exactly what the approver must see."""

    loan_id: str
    run_id: str
    recommendation: str
    conditions: list[dict[str, Any]]
    critic: dict[str, Any]
    capacity: dict[str, Any]
    evidence_ids: list[str]
    limited: bool
    issues: list[str]
    sla_hours: int = 24


@dataclass
class UnderwriterDecision:
    approved: bool
    underwriter: str = "uw-human"
    reason: str = ""
    remove_condition_ids: list[str] = field(default_factory=list)
