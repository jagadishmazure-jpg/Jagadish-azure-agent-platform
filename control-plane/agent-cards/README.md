# `control-plane/agent-cards/`: generated A2A agent cards

The checked-in A2A 1.0 agent cards for every agent in the catalog, plus the directory policy.
They are **generated** from `agentplatform.a2a.catalog` by
[`scripts/export_agent_cards.py`](../../scripts/export_agent_cards.py); CI and
`tests/test_a2a.py::test_checked_in_cards_are_current` fail if they drift from the code.
Control-plane metadata (owner, stage, side-effect class, allowed callers, tenants, eval score,
prompt refs, stand-in flag) rides in an `AgentExtension`, because the 1.0 card has no free-form
metadata field. Do not edit these files by hand.

| File | What it does |
|---|---|
| [`_policy.json`](_policy.json) | Directory policy per agent: `allowed_callers`, `stage` and `standin` flag. |
| [`crm-agent.json`](crm-agent.json) | First-party CRM domain agent (`get_borrower_profile` read, `create_followup_task` write). |
| [`dynamics-crm-standin.json`](dynamics-crm-standin.json) | **Stand-in** with a Dynamics 365-style shape (`get_contact`, `create_activity`). Not vendor software; makes no vendor API calls. |
| [`erp-agent.json`](erp-agent.json) | First-party ERP domain agent (`get_fee_ledger` read, `post_fee_invoice` write). |
| [`salesforce-crm-standin.json`](salesforce-crm-standin.json) | **Stand-in** with a Salesforce-style shape (`get_lead`, `create_task`). Not vendor software. |
| [`sap-erp-standin.json`](sap-erp-standin.json) | **Stand-in** with an SAP-style shape (`get_billing_document`, `simulate_posting`, and `commit_posting`, which requires human approval). Not vendor software. |
| [`underwriting-agent.json`](underwriting-agent.json) | The mortgage underwriting flagship exposed over A2A (`submit_loan_file`, `get_status`). |

## Regenerate / check

```bash
python scripts/export_agent_cards.py           # rewrite the JSON files from the catalog
python scripts/export_agent_cards.py --check   # exit 1 if any card is stale (CI step)
```

The checker only compares the files it renders, so this README does not affect it. At runtime
the same cards are served by each agent at `/.well-known/agent-card.json` and listed by the
BFF at `GET /directory`.
