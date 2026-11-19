"""Synthetic commercial-loan files. No real customer, account, or bureau data."""

from __future__ import annotations

from dataclasses import dataclass

APPLICATIONS: dict[str, dict] = {
    "APP-4401": {
        "application_id": "APP-4401",
        "borrower": "Northwind Outfitters LLC",
        "product": "commercial_term_loan",
        "principal": "250000.00",
        "annual_rate": "0.085",
        "term_months": 60,
        "monthly_noi": "20000.00",
        "existing_debt_service": "2500.00",
        "min_dscr": "1.25",
        "credit_consent": True,
        "permissible_purpose": "commercial_credit",
        "bureau_score": 718,
        "relationship_exposure": "40000.00",
        "synthetic": True,
    },
    "APP-4402": {
        "application_id": "APP-4402",
        "borrower": "Contoso Studio LLC",
        "product": "commercial_term_loan",
        "principal": "80000.00",
        "annual_rate": "0.09",
        "term_months": 36,
        "monthly_noi": "6000.00",
        "existing_debt_service": "900.00",
        "min_dscr": "1.25",
        "credit_consent": False,
        "permissible_purpose": "commercial_credit",
        "bureau_score": 690,
        "relationship_exposure": "0.00",
        "synthetic": True,
    },
}


@dataclass(frozen=True)
class KnowledgeItem:
    """A policy document the bank supplies. The harness does not invent one."""

    id: str
    text: str
    min_dscr: str


CREDIT_POLICY = KnowledgeItem(
    id="CREDIT-POLICY-SMB",
    text=(
        "Small-business term loans require a minimum DSCR of 1.25 on a fully amortizing payment. "
        "An insurance binder is required before booking. A named credit officer must approve before "
        "any commitment is recorded. The model draft is not the decision."
    ),
    min_dscr="1.25",
)

AGENT_INSTRUCTIONS = (
    "You are a commercial-loan assistant for a bank. Use only the supplied credit policy and the "
    "tool results. Do not calculate a substitute payment. Do not book a loan. A named credit officer "
    "decides, and the booking tool refuses a write that does not name that officer."
)
