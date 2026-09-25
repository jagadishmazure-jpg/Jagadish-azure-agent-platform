"""Five-exit failure handling: every node exits via success, retry, compensate, degrade, or escalate.

The table is data (FAILURE_TABLE) so docs, tests, and the graph all read the same source.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agentplatform.harness.budgets import BudgetExceeded
from agentplatform.harness.killswitch import AgentDisabled
from agentplatform.harness.resilience import CircuitBreaker, CircuitOpen, TransientError, retry_async


class Exit(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"  # succeeded after >=1 retry
    COMPENSATE = "compensate"  # partial side effect undone, then escalated
    DEGRADE = "degrade"  # limited-but-true answer; evidence-dependent writes disabled
    ESCALATE = "escalate"  # human / another system takes over


@dataclass
class NodeOutcome:
    node: str
    exit: Exit
    value: Any = None
    retries: int = 0
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.exit in (Exit.SUCCESS, Exit.RETRY)

    @property
    def limited(self) -> bool:
        return self.exit == Exit.DEGRADE


@dataclass
class FailurePolicy:
    node: str
    attempts: int = 3
    timeout_s: float = 20.0
    degrade: Callable[[BaseException], Awaitable[Any]] | None = None
    compensate: Callable[[BaseException], Awaitable[None]] | None = None
    breaker: CircuitBreaker | None = None
    retry_on: tuple[type[BaseException], ...] = field(
        default_factory=lambda: (TransientError, TimeoutError, ConnectionError)
    )


async def run_with_exits(policy: FailurePolicy, fn: Callable[[], Awaitable[Any]]) -> NodeOutcome:
    try:
        value, retries = await retry_async(
            fn,
            attempts=policy.attempts,
            timeout_s=policy.timeout_s,
            breaker=policy.breaker,
            retry_on=policy.retry_on,
        )
        return NodeOutcome(policy.node, Exit.RETRY if retries else Exit.SUCCESS, value, retries)
    except (BudgetExceeded, AgentDisabled) as exc:  # stop conditions are never retried or degraded
        return NodeOutcome(policy.node, Exit.ESCALATE, reason=str(exc))
    except Exception as exc:
        if policy.compensate is not None:
            await policy.compensate(exc)
            return NodeOutcome(policy.node, Exit.COMPENSATE, reason=f"compensated after: {exc!r}")
        if policy.degrade is not None:
            reason = "circuit open" if isinstance(exc, CircuitOpen) else repr(exc)
            return NodeOutcome(policy.node, Exit.DEGRADE, await policy.degrade(exc), reason=reason)
        return NodeOutcome(policy.node, Exit.ESCALATE, reason=repr(exc))


# node -> (success, retry, compensate, degrade, escalate). Written before the code, per doctrine.
FAILURE_TABLE: dict[str, dict[str, str]] = {
    "intake": {
        "success": "All documents extracted with field confidence >= 0.80; CRM profile fetched over A2A.",
        "retry": "Document Intelligence 429/5xx: 3 attempts, jittered backoff, circuit breaker per endpoint.",
        "compensate": "n/a (read-only).",
        "degrade": "Low-confidence fields become a 'provide legible copy' condition instead of guessed values.",
        "escalate": "DI unavailable after retries: file suspended to processor queue with trace id.",
    },
    "income": {
        "success": "Qualifying income computed from W-2 + paystub YTD with guideline citation.",
        "retry": "Model endpoint 429: retry, then fallback deployment for the narrative only.",
        "compensate": "n/a (read-only).",
        "degrade": "Model down: deterministic calculator output + templated rationale (numbers never from the LLM).",
        "escalate": "Income docs contradictory (>10% variance) -> underwriter review condition.",
    },
    "assets": {
        "success": "Funds to close + reserves verified; large deposits flagged with citation.",
        "retry": "Transient DI/model errors retried.",
        "compensate": "n/a (read-only).",
        "degrade": "Missing statement page -> condition for complete statement.",
        "escalate": "Insufficient funds to close -> suspend, human decides.",
    },
    "credit": {
        "success": "Tri-merge pulled via credit-bureau MCP server (read-only, idempotent request id).",
        "retry": "Bureau timeout: 2 retries with the same request id (no duplicate hard pulls).",
        "compensate": "n/a (bureau pull is logged, not reversible; idempotency prevents a second pull).",
        "degrade": "Never: credit is required for a decision.",
        "escalate": "Bureau unavailable -> file suspended 'credit unavailable'; no decision issued.",
    },
    "knowledge": {
        "success": "Temporal + ACL-filtered guideline passages and graph neighborhood packed with source map.",
        "retry": "AI Search 503: retry with backoff.",
        "compensate": "n/a (read-only).",
        "degrade": "Search down: known-guideline cache for top conditions, answer marked LIMITED, decision disabled.",
        "escalate": "Index lag beyond SLA: page knowledge owner; underwriter sees 'guidelines stale' banner.",
    },
    "critic": {
        "success": "Every condition cites an in-force guideline present in the evidence pack.",
        "retry": "One repair pass: re-retrieve for uncited conditions.",
        "compensate": "n/a.",
        "degrade": "Uncited conditions are dropped from the letter and listed for the underwriter.",
        "escalate": "Second failure -> underwriter review with critic report (never burn more tokens arguing).",
    },
    "underwriter_review": {
        "success": "Underwriter approves conditions; graph resumes from checkpoint.",
        "retry": "n/a (human node).",
        "compensate": "n/a.",
        "degrade": "n/a.",
        "escalate": "Deny stores reason; SLA timeout resolves to 'suspend', never to silent approval.",
    },
    "decision_letter": {
        "success": "Letter rendered; LOS/ERP updates queued on Service Bus with idempotency key.",
        "retry": "Queue send retried.",
        "compensate": "Queue write fails after letter drafted -> letter voided, status reverted to 'in review'.",
        "degrade": "n/a (a letter is either correct or not issued).",
        "escalate": "Compensation performed -> ops alert with trace.",
    },
}
