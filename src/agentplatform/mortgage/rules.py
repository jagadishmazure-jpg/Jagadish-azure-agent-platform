"""Turn calculator output + the packed (as-of) guidelines into a recommendation and cited conditions."""

from __future__ import annotations

from datetime import date
from typing import Any

from agentplatform.context.builder import ContextPack
from agentplatform.mortgage.calculators import days_between

BASE_TOPICS = [
    "maximum debt-to-income ratio",
    "minimum credit score",
    "base employment income calculation",
    "paystub age verbal verification of employment",
    "reserves months housing payment",
    "large deposits sourcing",
    "bank statement requirements",
    "appraisal requirement",
]


def topics_for(state: Any) -> list[str]:
    topics = list(BASE_TOPICS)
    credit = state.credit.get("report", {})
    if credit.get("inquiries"):
        topics.append("recent credit inquiries letter of explanation")
    if credit.get("public_records"):
        topics.append("derogatory credit bankruptcy seasoning")
    if state.graph_paths:
        topics.append("non-arm's-length transaction relationship seller employer")
    if any(d.get("low_confidence") for d in state.documents.values()):
        topics.append("legibility completeness of documents")
    topics.append("investor overlay minimum score high DTI")
    return topics


def _cond(cid: str, category: str, text: str, gids: list[str | None], timing: str, agent: str) -> dict:
    return {
        "id": cid,
        "category": category,
        "text": text,
        "timing": timing,
        "guideline_ids": [g for g in gids if g],
        "source_agent": agent,
    }


def evaluate(state: Any, pack: ContextPack) -> tuple[str, dict[str, Any], list[dict]]:
    """Returns (recommendation, capacity, draft conditions). Never returns a denial."""
    loan, inc, ast, cr = state.loan, state.income, state.assets, state.credit.get("report", {})
    app_date = loan["application_date"]
    conditions: list[dict] = []
    reasons: list[str] = []

    r_dti = pack.rule("GL-DTI-200")
    r_score = pack.rule("GL-CR-100")
    r_res = pack.rule("GL-AST-220")
    r_ovl = pack.rule("GL-OVL-900")
    cid = lambda r: r["chunk_id"] if r else None  # noqa: E731

    ratio = state.capacity.get("dti")
    reserves = ast.get("reserves_months") or 0.0
    capacity: dict[str, Any] = {
        "dti": ratio,
        "reserves_months": ast.get("reserves_months"),
        "piti": state.capacity.get("piti"),
    }

    # --- DTI against the version in force on the application date -------------------------------
    if r_dti is None:
        reasons.append("DTI guideline not in evidence")
    else:
        max_dti = r_dti["max_dti"]
        extended = r_dti.get("max_dti_with_reserves")
        need = r_dti.get("reserve_months_required", 0)
        capacity.update(max_dti=max_dti, dti_rule=r_dti["chunk_id"])
        if ratio is not None and ratio > max_dti:
            if extended and ratio <= extended and reserves >= need:
                conditions.append(
                    _cond(
                        "C-CAP-RSV",
                        "assets",
                        f"DTI {ratio:.1%} exceeds {max_dti:.0%}; verify at least {need} months of reserves remain at closing.",
                        [cid(r_dti), cid(r_res)],
                        "PTF",
                        "assets-agent",
                    )
                )
            else:
                reasons.append(f"DTI {ratio:.1%} exceeds {max_dti:.0%} under {r_dti['chunk_id']}")

    # --- Credit score -------------------------------------------------------------------------------
    score = cr.get("representative_score")
    if r_score is None:
        reasons.append("credit score guideline not in evidence")
    elif score is not None:
        min_score = r_score["min_score"]
        if r_score.get("high_dti") and ratio and ratio > r_score["high_dti"]:
            min_score = r_score["min_score_high_dti"]
        capacity.update(min_score=min_score, score=score, score_rule=r_score["chunk_id"])
        if score < min_score:
            reasons.append(f"score {score} below {min_score} under {r_score['chunk_id']}")
    if r_ovl and ratio and score and ratio > r_ovl["applies_above_dti"] and score < r_ovl["min_score"]:
        conditions.append(
            _cond(
                "C-OVL-INV",
                "compliance",
                f"Investor {r_ovl['investor']} overlay requires {r_ovl['min_score']} at DTI above "
                f"{r_ovl['applies_above_dti']:.0%}; route to an alternative investor or restructure.",
                [cid(r_ovl)],
                "PTD",
                "credit-agent",
            )
        )

    # --- Income --------------------------------------------------------------------------------------
    r_inc, r_age = pack.rule("GL-INC-110"), pack.rule("GL-INC-120")
    if inc.get("declining"):
        conditions.append(
            _cond(
                "C-INC-LOE",
                "income",
                f"Provide a signed explanation of the income decline (YTD annualized ${inc['annualized_ytd']:,.0f} vs "
                f"W-2 ${inc['w2_annual']:,.0f}); qualifying income uses YTD only.",
                [cid(r_inc)],
                "PTD",
                "income-agent",
            )
        )
    paydate = inc.get("pay_date")
    if paydate and r_age and days_between(paydate, app_date) > r_age["paystub_max_age_days"]:
        conditions.append(
            _cond(
                "C-INC-STUB",
                "income",
                "Provide a paystub dated within 30 days of application.",
                [cid(r_age)],
                "PTD",
                "income-agent",
            )
        )
    conditions.append(
        _cond(
            "C-INC-VVOE",
            "income",
            "Verbal verification of employment within 10 business days prior to closing.",
            [cid(r_age)],
            "PTF",
            "income-agent",
        )
    )

    # --- Assets --------------------------------------------------------------------------------------
    r_ld = pack.rule("GL-AST-210")
    for i, t in enumerate(ast.get("large_deposits", []), start=1):
        conditions.append(
            _cond(
                f"C-AST-LD{i}",
                "assets",
                f"Source the ${float(t['deposit']):,.0f} deposit on {t['date']} ('{t['description']}') with documentation.",
                [cid(r_ld)],
                "PTD",
                "assets-agent",
            )
        )
    if not ast.get("verified", False):
        reasons.append("assets unverified: legible, complete bank statement required")
    elif not ast.get("sufficient_funds", True):
        reasons.append("insufficient verified funds to close")
    elif r_res and reserves < r_res["min_reserve_months"]:
        reasons.append(f"reserves {reserves} months below {r_res['min_reserve_months']}")

    # --- Credit events ---------------------------------------------------------------------------
    r_inq = pack.rule("GL-CR-140")
    if cr.get("inquiries") and r_inq:
        recent = [
            q
            for q in cr["inquiries"]
            if days_between(q["date"], cr["report_date"]) <= r_inq["inquiry_window_days"]
        ]
        if recent:
            names = ", ".join(q["creditor"] for q in recent)
            conditions.append(
                _cond(
                    "C-CR-INQ",
                    "credit",
                    f"Letter of explanation for recent credit inquiries ({names}); document any new debt.",
                    [cid(r_inq)],
                    "PTD",
                    "credit-agent",
                )
            )
    r_bk = pack.rule("GL-CR-130")
    for rec in cr.get("public_records", []):
        if rec["type"] == "chapter7_bankruptcy" and r_bk:
            years = (date.fromisoformat(app_date) - date.fromisoformat(rec["discharged"])).days / 365.25
            if years < r_bk["ch7_seasoning_years"]:
                reasons.append(f"Chapter 7 seasoning {years:.1f}y below {r_bk['ch7_seasoning_years']}y")
            conditions.append(
                _cond(
                    "C-CR-BK",
                    "credit",
                    f"Provide Chapter 7 discharge papers (discharged {rec['discharged']}).",
                    [cid(r_bk)],
                    "PTD",
                    "credit-agent",
                )
            )

    # --- Property / relationships (graph RAG) ----------------------------------------------------
    conditions.append(
        _cond(
            "C-PRP-APR",
            "property",
            "Full appraisal supporting the purchase price, dated within 120 days of the note.",
            [cid(pack.rule("GL-PRP-310"))],
            "PTD",
            "underwriting-agent",
        )
    )
    if state.graph_paths:
        path = " / ".join(state.graph_paths[0])
        conditions.append(
            _cond(
                "C-PRP-NAL",
                "property",
                f"Non-arm's-length relationship detected ({path}); obtain signed disclosure and employer-assistance review.",
                [cid(pack.rule("GL-PRP-300"))],
                "PTD",
                "underwriting-agent",
            )
        )

    # --- Documents --------------------------------------------------------------------------------
    for doc_id, d in state.documents.items():
        if d.get("low_confidence"):
            conditions.append(
                _cond(
                    f"C-DOC-{doc_id}",
                    "documentation",
                    f"Provide a complete, legible copy of {doc_id} (unreadable: {', '.join(d['low_confidence'])}).",
                    [cid(pack.rule("GL-DOC-400"))],
                    "PTD",
                    "intake-agent",
                )
            )

    capacity["blocking_reasons"] = reasons
    if pack.limited or any(v == "escalate" for v in state.exits.values()):
        rec = "suspended"
    elif reasons:
        rec = "referred"  # a human underwriter decides; the system never issues a denial
    else:
        rec = "approved_with_conditions"
    return rec, capacity, conditions
