"""Deterministic underwriting math (the 'data plane' of this domain). The LLM never computes money.
Rule thresholds come from the guideline version the context builder packed (temporal RAG)."""

from __future__ import annotations

from datetime import date
from typing import Any


def monthly_pi(principal: float, rate_pct: float, term_months: int) -> float:
    r = rate_pct / 100 / 12
    if r == 0:
        return principal / term_months
    return principal * r / (1 - (1 + r) ** -term_months)


def qualifying_income(paystub: dict[str, Any], w2: dict[str, Any], decline_threshold: float = 0.10) -> dict:
    ytd = float(paystub["YearToDateGrossPay"])
    period_end = date.fromisoformat(paystub["PayPeriodEndDate"])
    months_ytd = period_end.month + (0 if period_end.day >= 28 else -0.5)
    w2_annual = float(w2["WagesTipsAndOtherCompensation"])
    annualized = ytd / months_ytd * 12
    declining = annualized < w2_annual * (1 - decline_threshold)
    monthly = annualized / 12 if declining else (w2_annual + ytd) / (12 + months_ytd)
    return {
        "monthly_qualifying_income": round(monthly, 2),
        "annualized_ytd": round(annualized, 2),
        "w2_annual": w2_annual,
        "months_ytd": months_ytd,
        "declining": declining,
        "method": "ytd-only (declining)" if declining else "w2+ytd average",
    }


def asset_position(
    bank: dict[str, Any],
    loan: dict[str, Any],
    monthly_income: float,
    piti: float,
    large_deposit_ratio: float = 0.5,
) -> dict:
    balance = float(bank["EndingBalance"])
    down = float(loan["purchase_price"]) - float(loan["loan_amount"])
    funds_to_close = down + float(loan["estimated_closing_costs"])
    threshold = monthly_income * large_deposit_ratio
    large = [
        t
        for t in bank.get("Transactions") or []
        if "PAYROLL" not in t["description"].upper() and float(t.get("deposit", 0)) > threshold
    ]
    unsourced = sum(float(t["deposit"]) for t in large)
    usable = balance - unsourced  # unsourced large deposits are excluded until sourced
    reserves = max(usable - funds_to_close, 0.0)
    return {
        "ending_balance": balance,
        "funds_to_close": round(funds_to_close, 2),
        "large_deposit_threshold": round(threshold, 2),
        "large_deposits": large,
        "usable_assets": round(usable, 2),
        "sufficient_funds": usable >= funds_to_close,
        "reserves_months": round(reserves / piti, 2) if piti else 0.0,
    }


def dti(monthly_income: float, piti: float, liabilities: float) -> float:
    return round((piti + liabilities) / monthly_income, 4) if monthly_income else 1.0


def days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days
