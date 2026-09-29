"""Deterministic fact sheet for the orchestration scenario ("conditions review" of a loan file).

Every number comes from the same data plane the main underwriting workflow uses: the LOS seed, the
Document Intelligence extractor (fixtures offline), the credit-bureau MCP server through the tool gateway,
and the calculators. Agents in every orchestration pattern read these facts through tools; they never
compute money. `expected_flags` is the answer key the pattern comparison scores against."""

from __future__ import annotations

from datetime import date
from typing import Any

from agentplatform.docintel.extractor import get_extractor
from agentplatform.harness.tracing import span
from agentplatform.mcp_servers._data import seed
from agentplatform.mcp_servers.gateway import ToolGateway
from agentplatform.mortgage import calculators

# Demo thresholds for the synthetic scenario (not a published guideline).
DTI_LIMIT = 0.45
MIN_RESERVES_MONTHS = 2.0
INQUIRY_LOOKBACK_DAYS = 90

# flag -> (owning specialist, condition text)
FLAG_CATALOG: dict[str, tuple[str, str]] = {
    "declining_income": ("income", "Written explanation and 2 years of income history for declining pay"),
    "recent_inquiry": ("credit", "Letter of explanation for recent credit inquiry"),
    "dti_over_limit": ("credit", "DTI above demo limit: reduce liabilities or restructure loan"),
    "unsourced_deposit": ("assets", "Source documentation for large non-payroll deposit"),
    "insufficient_funds": ("assets", "Additional verified assets to cover funds to close"),
    "low_reserves": ("assets", "Verify post-closing reserves of at least 2 months PITI"),
}
LANES = ("income", "credit", "assets")


def _fields(doc_id: str, doc_type: str) -> dict[str, Any]:
    doc = get_extractor().extract(doc_id, doc_type)
    return {k: v.value for k, v in doc.fields.items()}


async def gather_facts(loan_id: str, gateway: ToolGateway | None = None) -> dict[str, Any]:
    """Build the fact sheet for one loan: income, credit (via MCP), assets, and the derived flags."""
    data = seed()
    if loan_id not in data["loans"]:
        raise KeyError(f"unknown loan {loan_id}")
    loan = data["loans"][loan_id]
    gw = gateway or ToolGateway()
    with span("orchestration.facts", loan=loan_id):
        stub = _fields(f"{loan_id}-paystub", "paystub")
        w2 = _fields(f"{loan_id}-w2", "w2")
        bank = _fields(f"{loan_id}-bank", "bank_statement")
        income = calculators.qualifying_income(stub, w2)
        report = await gw.call(
            "credit-bureau",
            "pull_tri_merge",
            {"borrower_id": loan["borrower_id"], "request_id": f"orch:{loan_id}:credit"},
        )
        pi = calculators.monthly_pi(loan["loan_amount"], loan["rate_pct"], loan["term_months"])
        piti = round(pi + loan["monthly_taxes_insurance_hoa"], 2)
        monthly = income["monthly_qualifying_income"]
        assets = calculators.asset_position(bank, loan, monthly, piti)
        ratio = calculators.dti(monthly, piti, report["monthly_liabilities"])
        app = date.fromisoformat(loan["application_date"])
        recent = [
            i
            for i in report["inquiries"]
            if 0 <= (app - date.fromisoformat(i["date"])).days <= INQUIRY_LOOKBACK_DAYS
        ]
    flags = {
        "income": ["declining_income"] if income["declining"] else [],
        "credit": (["recent_inquiry"] if recent else []) + (["dti_over_limit"] if ratio > DTI_LIMIT else []),
        "assets": (["unsourced_deposit"] if assets["large_deposits"] else [])
        + ([] if assets["sufficient_funds"] else ["insufficient_funds"])
        + (["low_reserves"] if assets["reserves_months"] < MIN_RESERVES_MONTHS else []),
    }
    return {
        "loan_id": loan_id,
        "borrower_id": loan["borrower_id"],
        "income": {
            "monthly_qualifying_income": monthly,
            "method": income["method"],
            "declining": income["declining"],
            "flags": flags["income"],
        },
        "credit": {
            "report_id": report["report_id"],
            "representative_score": report["representative_score"],
            "monthly_liabilities": report["monthly_liabilities"],
            "recent_inquiries": recent,
            "piti": piti,
            "dti": ratio,
            "flags": flags["credit"],
        },
        "assets": {
            "usable_assets": assets["usable_assets"],
            "funds_to_close": assets["funds_to_close"],
            "reserves_months": assets["reserves_months"],
            "large_deposits": assets["large_deposits"],
            "flags": flags["assets"],
        },
    }


def expected_flags(facts: dict[str, Any]) -> list[str]:
    return sorted(f for lane in LANES for f in facts[lane]["flags"])
