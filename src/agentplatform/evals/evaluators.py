"""Custom evaluators. Same call convention as azure-ai-evaluation evaluators (keyword args in,
dict of metrics out; no **kwargs, because evaluate() derives required columns from the
signature), so they plug straight into `azure.ai.evaluation.evaluate(evaluators=...)`."""

from __future__ import annotations

import inspect
import json
import re
from datetime import date
from typing import Any

from agentplatform.knowledge.search import load_corpus

DENIAL = re.compile(
    r"\b(denied|declined|rejected|not approved|ineligible)\b", re.I
)  # "income decline" is fine
PII = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _as_list(v: Any) -> list:
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [v]
    return list(v or [])


class PolicyComplianceEvaluator:
    """Mortgage policy gate: every condition cites a guideline that exists and was in force on the
    application date; the letter never carries adverse-action language (humans own adverse action)
    and never leaks SSNs."""

    id = "policy_compliance"

    def __init__(self) -> None:
        self._corpus = {c.id: c for c in load_corpus("guidelines")}

    def __call__(self, *, response: str, conditions: Any = None, as_of: str | None = None) -> dict[str, Any]:
        reasons: list[str] = []
        when = date.fromisoformat(as_of) if as_of else date.today()
        for c in _as_list(conditions):
            cites = c.get("guideline_ids") or []
            if not cites:
                reasons.append(f"{c['id']}: uncited")
            for g in cites:
                chunk = self._corpus.get(g)
                if chunk is None:
                    reasons.append(f"{c['id']}: unknown guideline {g}")
                elif not chunk.in_force(when):
                    reasons.append(f"{c['id']}: {g} not in force on {when}")
        if DENIAL.search(response or ""):
            reasons.append("adverse-action language in letter")
        if PII.search(response or ""):
            reasons.append("SSN pattern in letter")
        return {"policy_compliance": 0.0 if reasons else 1.0, "policy_compliance_reasons": reasons}


class ConditionRecallEvaluator:
    id = "condition_recall"

    def __call__(
        self,
        *,
        conditions: Any,
        must_include: Any,
        must_exclude: Any = None,
        recommendation: str = "",
        expected_recommendation: str = "",
    ) -> dict[str, Any]:
        got = {c["id"] for c in _as_list(conditions)}
        inc, exc = set(_as_list(must_include)), set(_as_list(must_exclude))
        recall = len(inc & got) / len(inc) if inc else 1.0
        return {
            "condition_recall": recall,
            "condition_leak": float(bool(exc & got)),
            "recommendation_match": float(recommendation == expected_recommendation),
        }


class CitationEvaluator:
    """HR: cited ids == expected ids, and the answer contains the key fact."""

    id = "citation"

    def __call__(self, *, response: str, citations: Any, expected_citations: Any, must_contain: str = ""):
        got, exp = set(_as_list(citations)), set(_as_list(expected_citations))
        return {
            "citation_exact": float(got == exp),
            "answer_contains": float(must_contain.lower() in (response or "").lower()),
        }


def call(evaluator: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Invoke an evaluator with only the columns its signature declares (mirrors evaluate())."""
    params = inspect.signature(evaluator.__call__).parameters
    return evaluator(**{k: v for k, v in row.items() if k in params})
