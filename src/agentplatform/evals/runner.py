"""Generate eval rows by running the real targets, then score (offline or with azure-ai-evaluation).

Rows use the azure-ai-evaluation column names (`query`, `response`, `context`, `ground_truth`) so the
same JSONL feeds GroundednessEvaluator / RelevanceEvaluator unchanged."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from agent_framework import InMemoryCheckpointStorage

from agentplatform.evals.evaluators import (
    CitationEvaluator,
    ConditionRecallEvaluator,
    PolicyComplianceEvaluator,
    call,
)
from agentplatform.harness.identity import Principal
from agentplatform.knowledge.search import load_corpus
from agentplatform.mcp_servers._data import seed
from agentplatform.mortgage.models import UnderwriterDecision
from agentplatform.mortgage.service import UnderwritingService
from agentplatform.single.hr_agent import ask_hr

GOLDEN = Path(__file__).parent / "golden"

# Release gate (doctrine: an agent is promoted only if it clears its eval thresholds).
THRESHOLDS = {
    "policy_compliance": 1.0,
    "condition_recall": 0.95,
    "condition_leak": 0.0,  # max
    "recommendation_match": 1.0,
    "citation_exact": 0.8,
    "answer_contains": 0.8,
}
MAX_METRICS = {"condition_leak"}


def load_golden(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (GOLDEN / f"{name}.jsonl").read_text().splitlines() if line.strip()]


async def mortgage_rows() -> list[dict[str, Any]]:
    corpus = {c.id: c.content for c in load_corpus("guidelines")}
    loans = seed()["loans"]
    rows = []
    for g in load_golden("mortgage_conditions"):
        svc = UnderwritingService(storage=InMemoryCheckpointStorage())
        rec = await svc.start(g["loan_id"], Principal("eval", "contoso-mortgage", frozenset(g["groups"])))
        rec = await svc.decide(rec.run_id, UnderwriterDecision(True, "eval-uw", "golden run"))
        out = rec.outcome or {}
        letter = out.get("letter") or {}
        conds = out.get("conditions") or []
        cited = sorted({gid for c in conds for gid in c["guideline_ids"]})
        rows.append(
            {
                "id": g["id"],
                "query": f"Underwrite loan {g['loan_id']} and list conditions with citations.",
                "response": letter.get("body", "")
                + "\n"
                + "\n".join(f"- {c['text']} [{', '.join(c['guideline_ids'])}]" for c in conds),
                "context": "\n".join(f"[{gid}] {corpus.get(gid, '')}" for gid in cited),
                "conditions": conds,
                "recommendation": out.get("recommendation", ""),
                "as_of": loans[g["loan_id"]]["application_date"],
                **{k: g[k] for k in ("expected_recommendation", "must_include", "must_exclude")},
            }
        )
    return rows


async def hr_rows() -> list[dict[str, Any]]:
    corpus = {c.id: c.content for c in load_corpus("hr_policies")}
    rows = []
    for g in load_golden("hr_policy"):
        ans = await ask_hr(
            g["query"], Principal("eval", "contoso", frozenset(g["groups"])), date.fromisoformat(g["as_of"])
        )
        rows.append(
            {
                "id": g["id"],
                "query": g["query"],
                "response": ans.answer,
                "context": "\n".join(f"[{c}] {corpus[c]}" for c in ans.citations) or "(no passages)",
                "ground_truth": g["must_contain"],
                "citations": ans.citations,
                "expected_citations": g["expected_citations"],
                "must_contain": g["must_contain"],
            }
        )
    return rows


@dataclass
class EvalReport:
    metrics: dict[str, float]
    failures: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def score_offline(mortgage: list[dict], hr: list[dict]) -> EvalReport:
    per_row: list[dict[str, Any]] = []
    policy, recall, cite = PolicyComplianceEvaluator(), ConditionRecallEvaluator(), CitationEvaluator()
    for r in mortgage:
        per_row.append({"id": r["id"], **call(policy, r), **call(recall, r)})
    for r in hr:
        per_row.append({"id": r["id"], **call(cite, r)})
    metrics: dict[str, float] = {}
    for k in THRESHOLDS:
        vals = [row[k] for row in per_row if k in row]
        if vals:
            metrics[k] = max(vals) if k in MAX_METRICS else sum(vals) / len(vals)
    failures = [
        f"{k}={v:.2f} (threshold {'<=' if k in MAX_METRICS else '>='} {THRESHOLDS[k]})"
        for k, v in metrics.items()
        if (v > THRESHOLDS[k] if k in MAX_METRICS else v < THRESHOLDS[k])
    ]
    return EvalReport(metrics, failures, per_row)


def score_azure(
    rows_path: Path, project_endpoint: str, aoai_endpoint: str, deployment: str
) -> dict[str, Any]:
    """Foundry evaluation: built-in AI-assisted evaluators + our custom one, results logged to the project."""
    from azure.ai.evaluation import GroundednessEvaluator, RelevanceEvaluator, evaluate

    from agentplatform.config import azure_credential

    cred = azure_credential()
    model_config = {
        "azure_endpoint": aoai_endpoint,
        "azure_deployment": deployment,
        "api_version": "2024-10-21",
    }
    result = evaluate(
        data=str(rows_path),
        evaluation_name="mortgage-conditions-golden",
        evaluators={
            "groundedness": GroundednessEvaluator(model_config, credential=cred),
            "relevance": RelevanceEvaluator(model_config, credential=cred),
            "policy": PolicyComplianceEvaluator(),
        },
        evaluator_config={
            "groundedness": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}",
                    "context": "${data.context}",
                }
            },
            "relevance": {"column_mapping": {"query": "${data.query}", "response": "${data.response}"}},
            "policy": {
                "column_mapping": {
                    "response": "${data.response}",
                    "conditions": "${data.conditions}",
                    "as_of": "${data.as_of}",
                }
            },
        },
        azure_ai_project=project_endpoint,
        tags={"repo": "azure-agent-platform"},
    )
    return {"metrics": result["metrics"], "studio_url": result.get("studio_url")}
