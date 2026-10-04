# `safety/`: content safety gate

Screens what users send and what the system retrieves or extracts, to catch harmful content
and indirect prompt injection. Offline it uses deterministic pattern checks. On Azure it calls
`azure-ai-contentsafety` text analysis for harm categories and the Prompt Shields REST API
(`text:shieldPrompt`, api-version `2024-09-01`) for attacks, both with Entra ID, no keys.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Exports `get_safety_gate`. |
| [`content_safety.py`](content_safety.py) | `ContentSafetyGate` (`check_inbound`, `check_documents`), `SafetyVerdict` and `get_safety_gate()`. |

Used by the BFF on inbound chat text and by the context builder on retrieved passages. Tests: `pytest tests/test_harness.py -k safety` and `tests/test_single_agents.py -k injection`.
