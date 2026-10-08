# `docs/`: design and operations documents

Longer-form documentation that backs up the root README: the four-plane architecture, the
multi-agent orchestration pattern comparison, how the
engineering layers map to code, the generated five-exit failure table, the deployment path,
the billing model per resource (with no price figures on purpose) and notes on which SDK
versions and API shapes were verified.

| File | What it does |
|---|---|
| [`security/`](security/README.md) | Threat model: STRIDE, OWASP Top 10 for LLM Applications and MITRE ATLAS mapped to this repo's components, with controls, tests and built / planned status. |
| [`components/`](components/README.md) | One page per component with the 17 standard sections; output and code blocks are generated and checked by `scripts/doc_drift.py`. |
| [`implementation-guide.md`](implementation-guide.md) | Build order, layer by layer, with the proof command for each step. |
| [`adopt-this.md`](adopt-this.md) | What another team can take, how to configure it and how to extend it. |
| [`adr/`](adr/README.md) | Architecture decision records: one file per decision, with context, decision and consequences. |
| [`best-practices.md`](best-practices.md) | Enterprise cloud and agentic AI checklist for this repo, each item marked implemented, written-not-deployed or planned, with links to the code. |
| [`architecture.md`](architecture.md) | Four planes (experience, agent, knowledge, data): what changes on each, where it lives in the repo and which Azure service hosts it. |
| [`cost-estimate.md`](cost-estimate.md) | Resources, SKUs and billing dimensions for the `cost-min` and `standard` profiles. Deliberately contains no dollar amounts; links to official pricing pages and the calculator. |
| [`deploy.md`](deploy.md) | The laptop `azd up` path: prerequisites, profiles, kill switches, private networking, teardown. States up front that nothing has been deployed. |
| [`deployment.md`](deployment.md) | GitHub Actions pipeline: mermaid diagram, PR checks, dev -> prod with approval gates, Bicep or Terraform, OIDC federated-credential setup, smoke tests, teardown, and what a forward deployed engineer would do at a client. |
| [`engineering-layers.md`](engineering-layers.md) | Prompt, context, workflow, agent, graph, loop, harness and platform layers mapped to modules and to the tests that cover them. |
| [`failure-table.md`](failure-table.md) | Five-exit table (success, retry, compensate, degrade, escalate) per mortgage graph node. **Generated** from `agentplatform.harness.failure.FAILURE_TABLE` by `scripts/render_docs.py`; do not edit by hand. |
| [`orchestration-patterns.md`](orchestration-patterns.md) | MAF's five prebuilt orchestrations (sequential, concurrent, handoff, group chat, Magentic) on one loan conditions review: the builders and options used, a **generated** comparison and fault-drill table (`scripts/orchestrations_demo.py --compare --write`), and when to choose which. |
| [`sdk-notes.md`](sdk-notes.md) | What was checked against the real packages (Agent Framework, azure-ai-projects, a2a-sdk, mcp, Search, Document Intelligence, Content Safety, evaluation) and where the code differs from earlier assumptions. |

## Regenerate generated content

```bash
python scripts/render_docs.py      # rewrites docs/failure-table.md from FAILURE_TABLE
python scripts/doc_drift.py        # refreshes every output and code block in the Markdown files
python scripts/doc_drift.py --check   # what CI runs: fails if any pasted block is stale
```

> **Status:** nothing in this repo has been deployed to Azure yet. The Azure code paths follow verified SDK signatures but have only run offline; see the root README's *Honest limitations*.
