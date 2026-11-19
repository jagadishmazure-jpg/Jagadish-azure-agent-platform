"""Deterministic loan math. The model narrative never supplies these numbers."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")
ZERO = Decimal(0)
ONE = Decimal(1)
TWELVE = Decimal(12)


def monthly_payment(principal: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    if months <= 0:
        raise ValueError("months must be positive")
    if principal < ZERO:
        raise ValueError("principal must be non-negative")
    rate = annual_rate / TWELVE
    if rate == ZERO:
        return (principal / Decimal(months)).quantize(MONEY, rounding=ROUND_HALF_UP)
    growth = (ONE + rate) ** months
    raw = principal * rate * growth / (growth - ONE)
    return raw.quantize(MONEY, rounding=ROUND_HALF_UP)


def debt_service_coverage(monthly_noi: Decimal, existing_debt_service: Decimal, payment: Decimal) -> Decimal:
    total = existing_debt_service + payment
    if total <= ZERO:
        raise ValueError("debt service must be positive")
    return (monthly_noi / total).quantize(MONEY, rounding=ROUND_HALF_UP)
