# `docs/`: design and operations documents

Longer-form documentation that backs up the root README: the four-plane architecture, how the
engineering layers map to code, the generated five-exit failure table, the deployment path,
the billing model per resource (with no price figures on purpose) and notes on which SDK
versions and API shapes were verified.

| File | What it does |
|---|---|
| [`architecture.md`](architecture.md) | Four planes (experience, agent, knowledge, data): what changes on each, where it lives in the repo and which Azure service hosts it. |
| [`cost-estimate.md`](cost-estimate.md) | Resources, SKUs and billing dimensions for the `cost-min` and `standard` profiles. Deliberately contains no dollar amounts; links to official pricing pages and the calculator. |
| [`deploy.md`](deploy.md) | The intended `azd` deployment path, prerequisites and OIDC setup for `deploy.yml`. States up front that nothing has been deployed. |
| [`engineering-layers.md`](engineering-layers.md) | Prompt, context, workflow, agent, graph, loop, harness and platform layers mapped to modules and to the tests that cover them. |
| [`failure-table.md`](failure-table.md) | Five-exit table (success, retry, compensate, degrade, escalate) per mortgage graph node. **Generated** from `agentplatform.harness.failure.FAILURE_TABLE` by `scripts/render_docs.py`; do not edit by hand. |
| [`sdk-notes.md`](sdk-notes.md) | What was checked against the real packages (Agent Framework, azure-ai-projects, a2a-sdk, mcp, Search, Document Intelligence, Content Safety, evaluation) and where the code differs from earlier assumptions. |

## Regenerate the failure table

```bash
python scripts/render_docs.py      # rewrites docs/failure-table.md from FAILURE_TABLE
```

> **Status:** nothing in this repo has been deployed to Azure yet. The Azure code paths follow verified SDK signatures but have only run offline; see the root README's *Honest limitations*.
