"""Application service used by the BFF and the A2A underwriting agent: start, review, resume.

Durable by construction: every superstep is checkpointed; `resume()` rebuilds the graph from the
latest checkpoint (e.g., after a container restart) and re-surfaces the pending HITL request."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agent_framework import CheckpointStorage, FileCheckpointStorage, InMemoryCheckpointStorage, Workflow

from agentplatform.config import Settings, azure_credential, get_settings
from agentplatform.harness.identity import Principal, new_traceparent
from agentplatform.harness.tracing import span
from agentplatform.mortgage.models import (
    CHECKPOINT_TYPES,
    LoanRequest,
    UnderwriterDecision,
    UnderwriterReview,
)
from agentplatform.mortgage.workflow import Deps, build_workflow, new_run_id


def make_checkpoint_storage(
    settings: Settings | None = None, *, in_memory: bool = False
) -> CheckpointStorage:
    s = settings or get_settings()
    if in_memory:
        return InMemoryCheckpointStorage()
    if s.azure and s.cosmos_endpoint:
        from agent_framework_azure_cosmos import CosmosCheckpointStorage

        return CosmosCheckpointStorage(
            endpoint=s.cosmos_endpoint,
            database_name=s.cosmos_database,
            container_name="checkpoints",
            credential=azure_credential(s),
            allowed_checkpoint_types=CHECKPOINT_TYPES,
        )
    Path(s.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    return FileCheckpointStorage(s.checkpoint_dir, allowed_checkpoint_types=CHECKPOINT_TYPES)


@dataclass
class RunRecord:
    loan_id: str
    run_id: str
    tenant_id: str
    status: str = "running"
    pending_request_id: str | None = None
    review: dict[str, Any] | None = None
    requested_at: str | None = None
    outcome: dict[str, Any] | None = None


@dataclass
class UnderwritingService:
    deps: Deps = field(default_factory=Deps)
    storage: CheckpointStorage | None = None
    runs: dict[str, RunRecord] = field(default_factory=dict)
    _live: dict[str, Workflow] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.storage = self.storage or make_checkpoint_storage()

    def _wf(self, run_id: str) -> Workflow:
        if run_id not in self._live:
            self._live[run_id] = build_workflow(
                self.deps, run_name=f"mortgage-uw:{run_id}", checkpoint_storage=self.storage
            )
        return self._live[run_id]

    def _record(self, rec: RunRecord, result) -> RunRecord:
        outputs = result.get_outputs()
        pending = result.get_request_info_events()
        if outputs:
            rec.outcome = outputs[-1]
            rec.status = outputs[-1]["status"]
            rec.pending_request_id = None
        elif pending:
            ev = pending[0]
            rec.status = "awaiting_underwriter"
            rec.pending_request_id = ev.request_id
            review: UnderwriterReview = ev.data
            rec.review = json.loads(json.dumps(review.__dict__, default=str))
            rec.requested_at = rec.requested_at or datetime.now(UTC).isoformat()
        return rec

    async def start(self, loan_id: str, principal: Principal, traceparent: str | None = None) -> RunRecord:
        run_id = new_run_id(loan_id)
        rec = RunRecord(loan_id, run_id, principal.tenant_id)
        self.runs[run_id] = rec
        req = LoanRequest(
            loan_id,
            {
                "subject": principal.subject,
                "tenant_id": principal.tenant_id,
                "groups": sorted(principal.groups),
            },
            traceparent or new_traceparent(),
            run_id,
        )
        with span("underwriting.start", loan=loan_id, run=run_id, tenant=principal.tenant_id):
            result = await self._wf(run_id).run(req)
        return self._record(rec, result)

    async def decide(self, run_id: str, decision: UnderwriterDecision) -> RunRecord:
        rec = self.runs[run_id]
        if not rec.pending_request_id:
            raise ValueError(f"run {run_id} has no pending underwriter request")
        with span("underwriting.decide", run=run_id, approved=decision.approved):
            result = await self._wf(run_id).run(responses={rec.pending_request_id: decision})
        return self._record(rec, result)

    async def resume(self, run_id: str) -> RunRecord:
        """Rehydrate from the latest checkpoint in a fresh graph instance (process restart)."""
        self._live.pop(run_id, None)
        wf = self._wf(run_id)
        latest = await self.storage.get_latest(workflow_name=wf.name)
        if latest is None:
            raise KeyError(run_id)
        result = await wf.run(checkpoint_id=latest.checkpoint_id, checkpoint_storage=self.storage)
        rec = self.runs.setdefault(run_id, RunRecord(run_id.rsplit("-", 1)[0], run_id, "unknown"))
        return self._record(rec, result)

    async def expire_reviews(self, now: datetime | None = None) -> list[str]:
        """HITL SLA: an unanswered review resolves to 'return to processing' — never to silent approval."""
        now = now or datetime.now(UTC)
        expired = []
        for rec in list(self.runs.values()):
            if rec.status != "awaiting_underwriter" or not rec.requested_at:
                continue
            sla = timedelta(hours=(rec.review or {}).get("sla_hours", 24))
            if now - datetime.fromisoformat(rec.requested_at) >= sla:
                await self.decide(
                    rec.run_id, UnderwriterDecision(False, "sla-timer", "HITL SLA expired: auto-deny")
                )
                expired.append(rec.run_id)
        return expired
