# `tests/`: offline test suite

The pytest suite (116 tests). Everything runs offline: `conftest.py` forces `AAP_MODE=offline`,
writes file checkpoints to a temp directory instead of the working tree and resets the kill
switch around every test. A2A calls go through the in-process ASGI mesh; no Azure resources,
network or Docker are required.

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Sets `AAP_MODE=offline` and `AAP_CHECKPOINT_DIR` (temp dir); autouse fixture resets `KILL_SWITCH`. |
| [`test_a2a.py`](test_a2a.py) | Cards at well-known paths, stand-ins labelled, traceparent/tenant propagation, policy denial before the network and at the server, kill switch, write-HITL skills and idempotency, BFF to underwriting agent to CRM agent chain, promotion gate, checked-in cards current (10). |
| [`test_bff.py`](test_bff.py) | Underwrite then HITL decision, unknown loan rejected, directory and admin kill switch, chat endpoints and inbound safety (4). |
| [`test_evals.py`](test_evals.py) | Golden sets pass the release gate, policy evaluator catches violations, gate fails on regression, custom evaluator runs under `azure.ai.evaluation.evaluate()` offline, index definition matches the query contract, seed script dry run (6). |
| [`test_harness.py`](test_harness.py) | Budgets (identical calls, writes), traceparent propagation, kill-switch scopes, five exits, circuit breaker, failure table completeness, prompt pack versioning and schemas, offline safety gate, mock client structured draft (9). |
| [`test_infra.py`](test_infra.py) | Static deploy checks with no Azure calls: azure.yaml services match Container App tags, cost-min default with Private Link off, no local auth on data services, Bicep builds (4). |
| [`test_knowledge.py`](test_knowledge.py) | Version in force by date, confidential overlay hidden, reranker score range, OData filter syntax, context builder drops injection and cites, cache degrade, graph RAG non-arm's-length, Document Intelligence offline fields, redaction (9). |
| [`test_mcp.py`](test_mcp.py) | Small read-only tool surface, idempotent pull and transient mapping, gateway budget and errors, idempotent LOS queue, unreachable server maps to `TransientError` (5). |
| [`test_mortgage_workflow.py`](test_mortgage_workflow.py) | Happy path with cited in-force conditions, temporal RAG, graph RAG and ACL overlay, HITL deny stops before writes, resume after restart, kill switch between nodes, search/bureau/model outages, bureau retry with the same request id, critic repair and drop, outbox failure compensation, HITL SLA timeout, decision letter lists only approved conditions (17). |
| [`test_orchestrations.py`](test_orchestrations.py) | The five prebuilt MAF orchestrations: facts come from the data plane, every pattern × loan reaches the rule answer, sequential feedback re-runs the underwriter and resumes from a checkpoint, the concurrent missing lane refers, handoff routes only flagged lanes and asks the human for a missing loan id, the handoff persistence-flag requirement, the group chat round cap and checker, the orchestrator agent's per-round cost, Magentic plan revise, stall/reset/replan and round cap, the comparison doc is fresh (36). |
| [`test_repo_docs.py`](test_repo_docs.py) | Documentation structure: every component doc has the 17 sections in order and a mermaid diagram, the component index, implementation and adopt guides, a README in every folder, CODEOWNERS, no placeholders or prose dates, README test count equals the collected count, and the workflow supply-chain guard (pinned actions, permissions, gitleaks, CodeQL, Dependabot) (8). |
| [`test_single_agents.py`](test_single_agents.py) | HR cited and as-of aware, HR security trimming, HR injection blocked, IT ticket path, IT password reset requires approval, Foundry definitions dry run (6). |

Numbers in brackets are test counts from `pytest --collect-only`.

```bash
pytest -q                                   # all 116
pytest tests/test_mortgage_workflow.py -k outage
ruff check . && ruff format --check .       # lint, as in CI
```

`test_infra.py::test_bicep_builds_cleanly` needs the Bicep CLI (`bicep` on `PATH` or
`~/.azure/bin/bicep`, which `az bicep install` provides); it is skipped when neither exists.
