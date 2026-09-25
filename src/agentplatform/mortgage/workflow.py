"""Workflow + graph layers: the MAF graph for mortgage underwriting conditions.

    intake ──┬─> income ──┐
             ├─> credit ──┼─> join ─> assets ─> underwriting ─> critic ─┬─> repair ─> critic (max 1)
             └─> knowledge┘                                             └─> underwriter_review (HITL)
                                                                              └─> decision_letter

Every executor: kill-switch check, step budget, five-exit wrapper, OTel span. State is checkpointed
after every superstep (FileCheckpointStorage offline, CosmosCheckpointStorage on Azure)."""

from __future__ import annotations

import asyncio
import copy
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from agent_framework import (
    Case,
    CheckpointStorage,
    Default,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from agentplatform.context.builder import ContextBuilder, ContextPack
from agentplatform.docintel.extractor import DocumentExtractor, get_extractor
from agentplatform.harness.budgets import BudgetExceeded
from agentplatform.harness.failure import Exit, FailurePolicy, run_with_exits
from agentplatform.harness.identity import Principal, child_traceparent, trace_id_of
from agentplatform.harness.killswitch import KILL_SWITCH, AgentDisabled
from agentplatform.harness.outbox import InMemoryOutbox, Outbox, OutboxError
from agentplatform.harness.resilience import CircuitBreaker, TransientError
from agentplatform.harness.tracing import span
from agentplatform.knowledge.graph import EntityGraph, demo_graph
from agentplatform.knowledge.search import SearchBackend, SearchQuery, SearchUnavailable, get_search_backend
from agentplatform.mcp_servers.gateway import ToolError, ToolGateway
from agentplatform.mortgage import calculators, critic, rules
from agentplatform.mortgage.agents import AgentSuite
from agentplatform.mortgage.models import LoanRequest, UnderwriterDecision, UnderwriterReview, UWState
from agentplatform.safety.content_safety import ContentSafetyGate

AGENT_ID = "mortgage-underwriting"
MAX_STEPS = 20
MAX_CRITIC_REPAIRS = 1
REPAIR_MIN_RERANKER = 1.5  # semantic-ranker scale 0-4; below this a 'citation' is a guess
CrmLookup = Callable[[str, Principal, str], Awaitable[dict[str, Any]]]


@dataclass
class Deps:
    """Runtime dependencies (not checkpointed; rebuilt on resume)."""

    search: SearchBackend = field(default_factory=get_search_backend)
    graph: EntityGraph = field(default_factory=demo_graph)
    extractor: DocumentExtractor = field(default_factory=get_extractor)
    safety: ContentSafetyGate = field(default_factory=ContentSafetyGate)
    agents: AgentSuite = field(default_factory=AgentSuite)
    outbox: Outbox = field(default_factory=InMemoryOutbox)
    crm_lookup: CrmLookup | None = None
    search_breaker: CircuitBreaker = field(default_factory=lambda: CircuitBreaker("ai-search"))
    docintel_breaker: CircuitBreaker = field(default_factory=lambda: CircuitBreaker("docintel"))

    def builder(self) -> ContextBuilder:
        return ContextBuilder(self.search, graph=self.graph, safety=self.safety)


def _principal(state: UWState | LoanRequest) -> Principal:
    p = state.principal
    return Principal(p["subject"], p["tenant_id"], frozenset(p.get("groups", [])), agent_id=AGENT_ID)


class _Node(Executor):
    """Base: kill switch + step budget + halt output. Subclasses implement `work`."""

    node = "node"

    def __init__(self, deps: Deps, id: str | None = None) -> None:
        super().__init__(id=id or self.node)
        self.deps = deps

    async def _guard(self, state: UWState, ctx: WorkflowContext) -> bool:
        try:
            KILL_SWITCH.check(AGENT_ID, state.principal["tenant_id"])
            state.budget["steps"] = state.budget.get("steps", 0) + 1
            if state.budget["steps"] > MAX_STEPS:
                raise BudgetExceeded("max_steps", self.node)
            return True
        except (AgentDisabled, BudgetExceeded) as exc:
            state.exit(self.node, Exit.ESCALATE, str(exc))
            await ctx.yield_output(_outcome(state, status="halted", reason=str(exc)))
            return False


def _outcome(
    state: UWState, *, status: str, reason: str = "", letter: dict | None = None, **extra: Any
) -> dict:
    return {
        "loan_id": state.loan_id,
        "run_id": state.run_id,
        "status": status,
        "reason": reason,
        "recommendation": state.recommendation,
        "conditions": state.conditions,
        "letter": letter,
        "exits": state.exits,
        "issues": state.issues,
        "capacity": state.capacity,
        "trace_id": trace_id_of(state.traceparent),
        **extra,
    }


# ------------------------------------------------------------------------------------------ intake
class IntakeExecutor(_Node):
    node = "intake"

    @handler
    async def start(self, req: LoanRequest, ctx: WorkflowContext[UWState, dict]) -> None:
        state = UWState(req.loan_id, req.run_id, req.principal, child_traceparent(req.traceparent))
        if not await self._guard(state, ctx):
            return
        principal = _principal(state)
        with span("node.intake", tenant=principal.tenant_id, loan=req.loan_id, run=req.run_id):
            gw = ToolGateway()
            try:
                state.loan = await gw.call(
                    "los", "get_loan_file", {"loan_id": req.loan_id}, tenant=principal.tenant_id
                )
            except ToolError as exc:
                state.exit("intake", Exit.ESCALATE, str(exc))
                await ctx.yield_output(_outcome(state, status="rejected", reason="loan file not found"))
                return
            if self.deps.crm_lookup:  # A2A hop to the CRM domain agent (traceparent + tenant propagate)
                try:
                    state.crm = await self.deps.crm_lookup(
                        state.loan["borrower_id"], principal, state.traceparent
                    )
                except Exception as exc:  # CRM is enrichment, not required -> degrade
                    state.exit("crm", Exit.DEGRADE, f"CRM agent unavailable: {exc}")
            worst = Exit.SUCCESS
            for d in state.loan["documents"]:
                out = await run_with_exits(
                    FailurePolicy("intake", attempts=3, breaker=self.deps.docintel_breaker),
                    lambda d=d: asyncio.to_thread(self.deps.extractor.extract, d["doc_id"], d["doc_type"]),
                )
                if not out.ok:
                    state.exit("intake", Exit.ESCALATE, f"{d['doc_id']}: document intelligence unavailable")
                    worst = Exit.ESCALATE
                    continue
                doc = out.value
                if out.exit == Exit.RETRY and worst == Exit.SUCCESS:
                    worst = Exit.RETRY
                # OCR text is untrusted input too: screen string fields for indirect injection.
                strings = [str(v.value) for v in doc.fields.values() if isinstance(v.value, str | list)]
                if strings and not all(v.allowed for v in self.deps.safety.check_documents(strings)):
                    state.issues.append(f"intake: injection pattern in {doc.doc_id}; fields quarantined")
                    doc.fields = {k: v for k, v in doc.fields.items() if not isinstance(v.value, str | list)}
                low = doc.low_confidence()
                if low and worst in (Exit.SUCCESS, Exit.RETRY):
                    worst = Exit.DEGRADE
                state.documents[doc.doc_id] = {
                    "doc_type": doc.doc_type,
                    "model_id": doc.model_id,
                    "fields": {k: v.value for k, v in doc.fields.items() if v.confidence >= 0.80},
                    "low_confidence": low,
                }
            state.exits["intake"] = str(worst)
            state.narratives["intake"] = (
                await self.deps.agents.structured(
                    "intake",
                    facts={"documents": list(state.documents)},
                    draft={
                        "summary": f"Extracted {len(state.documents)} documents.",
                        "citations": list(state.documents),
                    },
                )
            )["summary"]
        await ctx.send_message(state)


def _doc(state: UWState, doc_type: str) -> dict[str, Any]:
    return next((d["fields"] for d in state.documents.values() if d["doc_type"] == doc_type), {})


# ---------------------------------------------------------------------------- fan-out: income/credit
class IncomeExecutor(_Node):
    node = "income"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        state = copy.deepcopy(state)
        state.lane = "income"
        if not await self._guard(state, ctx):
            return
        with span("node.income", loan=state.loan_id):
            stub, w2 = _doc(state, "paystub"), _doc(state, "w2")
            if (
                not {"YearToDateGrossPay", "PayPeriodEndDate"} <= set(stub)
                or "WagesTipsAndOtherCompensation" not in w2
            ):
                state.exit("income", Exit.ESCALATE, "income documents incomplete")
            else:
                state.income = calculators.qualifying_income(stub, w2)
                state.income["pay_date"] = stub.get("PayDate")
                n = await self.deps.agents.structured(
                    "income",
                    facts=state.income,
                    draft={
                        "summary": f"Qualifying income ${state.income['monthly_qualifying_income']:,.2f}/mo "
                        f"({state.income['method']}).",
                        "citations": ["GL-INC-110"],
                    },
                )
                state.narratives["income"] = n["summary"]
                state.exits["income"] = str(Exit.SUCCESS)
        await ctx.send_message(state)


class CreditExecutor(_Node):
    node = "credit"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        state = copy.deepcopy(state)
        state.lane = "credit"
        if not await self._guard(state, ctx):
            return
        gw = ToolGateway()
        request_id = f"{state.run_id}:credit"  # same id on every retry -> no duplicate hard pull
        with span("node.credit", loan=state.loan_id, tool="credit-bureau.pull_tri_merge"):
            out = await run_with_exits(
                FailurePolicy("credit", attempts=3),
                lambda: gw.call(
                    "credit-bureau",
                    "pull_tri_merge",
                    {"borrower_id": state.loan["borrower_id"], "request_id": request_id},
                    tenant=state.principal["tenant_id"],
                ),
            )
            state.exits["credit"] = str(out.exit)
            if out.ok:
                state.credit = {"report": out.value, "request_id": request_id}
                n = await self.deps.agents.structured(
                    "credit",
                    facts=out.value,
                    draft={
                        "summary": f"Representative score {out.value['representative_score']}; "
                        f"monthly liabilities ${out.value['monthly_liabilities']:,}.",
                        "citations": [out.value["report_id"]],
                    },
                )
                state.narratives["credit"] = n["summary"]
            else:
                state.issues.append(f"credit: bureau unavailable ({out.reason}); no decision can be issued")
        await ctx.send_message(state)


class KnowledgeExecutor(_Node):
    """Temporal + ACL guideline retrieval (as-of application date) and graph RAG over parties."""

    node = "knowledge"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        state = copy.deepcopy(state)
        state.lane = "knowledge"
        if not await self._guard(state, ctx):
            return
        principal = _principal(state)
        as_of = date.fromisoformat(state.loan["application_date"])
        borrower = f"borrower:{state.loan['borrower_id']}"
        with span("node.knowledge", loan=state.loan_id, as_of=as_of.isoformat()):
            paths = self.deps.graph.related_parties(borrower, set(state.loan.get("counterparties", [])))
            state.graph_paths = [
                [f"{e.subject} -[{e.relation}]-> {e.object} ({e.source_id})" for e in p] for p in paths
            ]
            builder = self.deps.builder()

            async def degrade(exc: BaseException) -> ContextPack:
                return builder.build_from_cache(principal=principal, as_of=as_of, reason=repr(exc))

            out = await run_with_exits(
                FailurePolicy(
                    "knowledge",
                    attempts=3,
                    breaker=self.deps.search_breaker,
                    degrade=degrade,
                    retry_on=(SearchUnavailable, TransientError, TimeoutError),
                ),
                lambda: asyncio.to_thread(
                    builder.build,
                    topics=rules.BASE_TOPICS,
                    principal=principal,
                    as_of=as_of,
                    program=state.loan.get("program"),
                    graph_anchor=borrower,
                    top_per_topic=2,
                ),
            )
            state.exits["knowledge"] = str(out.exit)
            state.evidence = out.value.to_dict() if out.value else {}
            if out.limited:
                state.issues.append("knowledge: AI Search degraded -> LIMITED evidence; decision disabled")
        await ctx.send_message(state)


class JoinExecutor(_Node):
    node = "join"

    @handler
    async def join(self, branches: list[UWState], ctx: WorkflowContext[UWState, dict]) -> None:
        by_lane = {b.lane: b for b in branches}
        state = copy.deepcopy(by_lane.get("income") or branches[0])
        for b in branches:
            state.exits.update(b.exits)
            state.issues += [i for i in b.issues if i not in state.issues]
            state.narratives.update(b.narratives)
            state.budget["steps"] = max(state.budget.get("steps", 0), b.budget.get("steps", 0))
        state.credit = by_lane["credit"].credit if "credit" in by_lane else {}
        state.evidence = by_lane["knowledge"].evidence if "knowledge" in by_lane else {}
        state.graph_paths = by_lane["knowledge"].graph_paths if "knowledge" in by_lane else []
        state.lane = ""
        if not await self._guard(state, ctx):
            return
        await ctx.send_message(state)


class AssetsExecutor(_Node):
    node = "assets"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        if not await self._guard(state, ctx):
            return
        loan = state.loan
        pi = calculators.monthly_pi(loan["loan_amount"], loan["rate_pct"], loan["term_months"])
        piti = round(pi + loan["monthly_taxes_insurance_hoa"], 2)
        state.capacity["piti"] = piti
        bank = _doc(state, "bank_statement")
        income = state.income.get("monthly_qualifying_income", 0.0)
        pack = ContextPack.from_dict(state.evidence) if state.evidence else None
        ld_rule = pack.rule("GL-AST-210") if pack else None
        if "EndingBalance" not in bank:
            state.exit("assets", Exit.DEGRADE, "ending balance unreadable -> legible statement condition")
            state.assets = {"verified": False, "reserves_months": None, "large_deposits": []}
        else:
            ratio = ld_rule["large_deposit_ratio"] if ld_rule else 0.5
            state.assets = {"verified": True, **calculators.asset_position(bank, loan, income, piti, ratio)}
            state.exits["assets"] = str(Exit.SUCCESS)
        n = await self.deps.agents.structured(
            "assets",
            facts=state.assets,
            draft={
                "summary": f"Reserves {state.assets.get('reserves_months', 0)} months; "
                f"{len(state.assets.get('large_deposits', []))} large deposit(s) to source.",
                "citations": [c for c in ["GL-AST-210", "GL-AST-220"] if pack and pack.rule(c)],
            },
        )
        state.narratives["assets"] = n["summary"]
        await ctx.send_message(state)


class UnderwritingExecutor(_Node):
    """Capacity (DTI), conditional retrieval for findings, rules -> recommendation + cited conditions."""

    node = "underwriting"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        if not await self._guard(state, ctx):
            return
        income = state.income.get("monthly_qualifying_income")
        liabilities = state.credit.get("report", {}).get("monthly_liabilities", 0)
        state.capacity["dti"] = (
            calculators.dti(income, state.capacity["piti"], liabilities) if income else None
        )
        pack = (
            ContextPack.from_dict(state.evidence)
            if state.evidence
            else ContextPack(as_of=date.fromisoformat(state.loan["application_date"]), limited=True)
        )
        extra = [t for t in rules.topics_for(state) if t not in pack.queries]
        if extra and not pack.limited:
            try:
                more = await asyncio.to_thread(
                    self.deps.builder().build,
                    topics=extra,
                    principal=_principal(state),
                    as_of=pack.as_of,
                    program=state.loan.get("program"),
                    top_per_topic=2,
                )
                pack.merge(more)
            except SearchUnavailable as exc:
                pack.limited = True
                state.issues.append(f"underwriting: follow-up retrieval failed ({exc}); LIMITED")
        state.evidence = pack.to_dict()
        rec, capacity, draft = rules.evaluate(state, pack)
        state.capacity.update(capacity)
        state.recommendation = rec
        polished = await self.deps.agents.structured(
            "conditions",
            facts={"capacity": state.capacity},
            draft={"conditions": draft},
            evidence=pack.render(),
        )
        state.conditions = polished["conditions"]
        await ctx.send_message(state)


# ------------------------------------------------------------------------------------ loop: critic
class CriticExecutor(_Node):
    node = "critic"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        if not await self._guard(state, ctx):
            return
        pack = ContextPack.from_dict(state.evidence)
        report = critic.check(state.conditions, pack, pack.as_of)
        attempts = state.critic.get("repairs", 0)
        report["repairs"] = attempts
        failing = set(report["uncited"] + report["not_in_evidence"] + report["not_in_force"])
        if not report["passed"] and attempts >= MAX_CRITIC_REPAIRS:
            # degrade: drop uncited conditions from the letter; escalate: underwriter sees the list
            report["dropped"] = [c for c in state.conditions if c["id"] in failing]
            state.conditions = [c for c in state.conditions if c["id"] not in failing]
            state.exit("critic", Exit.ESCALATE, f"critic failed after repair: {sorted(failing)}")
        else:
            state.exits["critic"] = str(Exit.SUCCESS if attempts == 0 else Exit.RETRY)
        report["needs_repair"] = not report["passed"] and attempts < MAX_CRITIC_REPAIRS
        state.critic = report
        await ctx.send_message(state)


class RepairExecutor(_Node):
    """Agentic RAG, capped: re-retrieve with each failing condition's text and re-cite if found."""

    node = "repair"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        if not await self._guard(state, ctx):
            return
        pack = ContextPack.from_dict(state.evidence)
        failing = set(
            state.critic["uncited"] + state.critic["not_in_evidence"] + state.critic["not_in_force"]
        )
        principal = _principal(state)
        for c in state.conditions:
            if c["id"] not in failing:
                continue
            hits = await asyncio.to_thread(
                self.deps.search.search, SearchQuery(c["text"], pack.as_of, principal.groups, top=1)
            )
            if hits and hits[0].reranker_score >= REPAIR_MIN_RERANKER:
                more = self.deps.builder()
                more_pack = ContextPack(as_of=pack.as_of)
                more._pack_guidelines(more_pack, [hits[0].chunk], principal, pack.as_of)
                pack.merge(more_pack)
                if more_pack.items:
                    c["guideline_ids"] = [more_pack.items[0].source_id]
        state.evidence = pack.to_dict()
        state.critic["repairs"] = state.critic.get("repairs", 0) + 1
        await ctx.send_message(state)


# -------------------------------------------------------------------------------- HITL + finalizer
class UnderwriterReviewExecutor(_Node):
    node = "underwriter_review"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        if not await self._guard(state, ctx):
            return
        ctx.set_state("uw_state", state)
        pack = ContextPack.from_dict(state.evidence)
        await ctx.request_info(
            UnderwriterReview(
                loan_id=state.loan_id,
                run_id=state.run_id,
                recommendation=state.recommendation,
                conditions=state.conditions,
                critic=state.critic,
                capacity=state.capacity,
                evidence_ids=pack.ids(),
                limited=pack.limited,
                issues=state.issues,
            ),
            UnderwriterDecision,
        )

    @response_handler
    async def on_decision(
        self, review: UnderwriterReview, decision: UnderwriterDecision, ctx: WorkflowContext[UWState, dict]
    ) -> None:
        state: UWState = ctx.get_state("uw_state")
        if not decision.approved:
            state.exits["underwriter_review"] = str(Exit.ESCALATE)
            await ctx.yield_output(
                _outcome(
                    state,
                    status="returned_to_processing",
                    reason=decision.reason or "denied by underwriter",
                    underwriter=decision.underwriter,
                )
            )
            return
        state.exits["underwriter_review"] = str(Exit.SUCCESS)
        state.conditions = [c for c in state.conditions if c["id"] not in set(decision.remove_condition_ids)]
        state.narratives["underwriter"] = f"approved by {decision.underwriter}"
        await ctx.send_message(state)


class DecisionLetterExecutor(_Node):
    node = "decision_letter"

    @handler
    async def run(self, state: UWState, ctx: WorkflowContext[UWState, dict]) -> None:
        if not await self._guard(state, ctx):
            return
        decision = state.recommendation or "suspended"
        pack = ContextPack.from_dict(state.evidence)
        cites = sorted({g for c in state.conditions for g in c["guideline_ids"]})
        body = (
            f"Dear {state.loan['borrower_name']}, your application {state.loan_id} is "
            + {
                "approved_with_conditions": "conditionally approved subject to the conditions below.",
                "suspended": "suspended pending the items below; no decision has been made.",
                "referred": "under review by an underwriter; we will contact you about next steps.",
            }[decision]
        )
        letter = await self.deps.agents.structured(
            "letter",
            facts={"decision": decision},
            draft={
                "loan_id": state.loan_id,
                "decision": decision,
                "body": body,
                "conditions": state.conditions,
                "citations": cites,
            },
            evidence=pack.render(),
        )
        key = f"{state.run_id}:{decision}"
        voided: list[str] = []

        async def compensate(exc: BaseException) -> None:
            if hasattr(self.deps.outbox, "void"):
                self.deps.outbox.void(key)
            # the LOS status was already queued -> queue the offsetting command (never a silent delete)
            await ToolGateway().call(
                "los",
                "queue_status_update",
                {"loan_id": state.loan_id, "status": "in_review", "idempotency_key": f"{key}:compensate"},
                write=True,
                tenant=state.principal["tenant_id"],
            )
            voided.append(repr(exc))

        async def queue_writes() -> dict:
            gw = ToolGateway()
            status = {"approved_with_conditions": "conditionally_approved"}.get(decision, "suspended")
            los = await gw.call(
                "los",
                "queue_status_update",
                {"loan_id": state.loan_id, "status": status, "idempotency_key": key},
                write=True,
                tenant=state.principal["tenant_id"],
            )
            try:
                self.deps.outbox.send(
                    "erp-postings",
                    {
                        "loan_id": state.loan_id,
                        "event": "decision_issued",
                        "decision": decision,
                        "traceparent": child_traceparent(state.traceparent),
                        "tenant": state.principal["tenant_id"],
                    },
                    key,
                )
            except OutboxError as exc:
                raise RuntimeError(f"outbox failed after LOS queued: {exc}") from exc
            return los

        out = await run_with_exits(
            FailurePolicy("decision_letter", attempts=1, compensate=compensate), queue_writes
        )
        state.exits["decision_letter"] = str(out.exit)
        if out.exit == Exit.COMPENSATE:
            state.issues.append(
                f"decision_letter: compensated ({voided[0]}); letter voided, status in_review"
            )
            await ctx.yield_output(_outcome(state, status="in_review", reason="write failed; compensated"))
            return
        await ctx.yield_output(_outcome(state, status="decision_issued", letter=letter, los_ticket=out.value))


# ------------------------------------------------------------------------------------------- build
def build_workflow(
    deps: Deps, *, run_name: str, checkpoint_storage: CheckpointStorage | None = None
) -> Workflow:
    intake = IntakeExecutor(deps)
    income, credit, knowledge = IncomeExecutor(deps), CreditExecutor(deps), KnowledgeExecutor(deps)
    join, assets, uw = JoinExecutor(deps), AssetsExecutor(deps), UnderwritingExecutor(deps)
    crit, repair = CriticExecutor(deps), RepairExecutor(deps)
    review, letter = UnderwriterReviewExecutor(deps), DecisionLetterExecutor(deps)
    return (
        WorkflowBuilder(
            start_executor=intake,
            checkpoint_storage=checkpoint_storage,
            name=run_name,  # per-run name -> per-run checkpoint partition (Cosmos pk = workflow_name)
            description="Mortgage underwriting conditions (MAF graph)",
            max_iterations=40,
        )
        .add_fan_out_edges(intake, [income, credit, knowledge])
        .add_fan_in_edges([income, credit, knowledge], join)
        .add_edge(join, assets)
        .add_edge(assets, uw)
        .add_edge(uw, crit)
        .add_switch_case_edge_group(
            crit,
            [
                Case(condition=lambda s: bool(s.critic.get("needs_repair")), target=repair),
                Default(target=review),
            ],
        )
        .add_edge(repair, crit)
        .add_edge(review, letter)
        .build()
    )


def new_run_id(loan_id: str) -> str:
    return f"{loan_id}-{uuid.uuid4().hex[:8]}"
