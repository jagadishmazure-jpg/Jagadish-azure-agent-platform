# Implementation guide

How the platform is built, layer by layer, in the order you would build it again. Each step names the files, the command that proves it works and the test that keeps it working. Everything here runs offline (`AAP_MODE=offline`, the default); the last step describes the Azure switch.

## 1. Set up

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
make lint && make test
```

`pyproject.toml` pins Microsoft Agent Framework, a2a-sdk, mcp and the Azure SDKs to the versions recorded in [`sdk-notes.md`](sdk-notes.md).

## 2. Configuration in one place

`src/agentplatform/config.py` maps environment variables (the `azd` outputs) to adapters. Every module asks `get_settings()`; nothing else reads `os.environ`. `AAP_MODE` decides whether each adapter is a deterministic mock or its Azure service, and `azure_credential()` is the only credential factory (managed identity, no keys).

## 3. Harness first

Before any agent, build what wraps every call: `Principal` and `traceparent` helpers, `Budget`, `KillSwitch`, `retry_async` with `CircuitBreaker`, the five-exit `FAILURE_TABLE` and `run_with_exits`, the outbox and `span()`. See [components/harness.md](components/harness.md). Proof: `pytest tests/test_harness.py`, and `python scripts/render_docs.py --check` keeps `docs/failure-table.md` generated from the table.

## 4. Prompts and model clients

Write prompts as Markdown with front matter in `prompts/pack/` and bind each to a schema in `prompts/schemas.py` ([components/prompts.md](components/prompts.md)). `llm/clients.py` gives a real MAF `BaseChatClient` mock offline and a Foundry client on Azure ([components/model-clients.md](components/model-clients.md)).

## 5. Knowledge, documents and safety

- Index schema with temporal and ACL fields, `build_odata_filter`, in-memory and AI Search backends, and the entity graph ([components/knowledge-and-context.md](components/knowledge-and-context.md)).
- `ContextBuilder`: retrieve per topic, screen passages, redact PII, pack and cite.
- Document Intelligence extractor with fixtures ([components/document-intelligence.md](components/document-intelligence.md)).
- Content Safety gate for inbound text and retrieved documents ([components/safety.md](components/safety.md)).

Proof: `pytest tests/test_knowledge.py`.

## 6. Tools and agent-to-agent calls

- MCP servers for the credit bureau and LOS, reached through `ToolGateway` ([components/mcp-tool-plane.md](components/mcp-tool-plane.md)).
- A2A catalog, directory policy, client and server factory; cards exported to `control-plane/agent-cards/` ([components/a2a-control-plane.md](components/a2a-control-plane.md)).

Proof: `pytest tests/test_mcp.py tests/test_a2a.py` and `python scripts/export_agent_cards.py --check`.

## 7. The flagship workflow

Build `mortgage/` in this order: calculators (pure functions), rules, critic, agents, executors, `build_workflow()`, then `UnderwritingService` with checkpoints and the human review ([components/mortgage-workflow.md](components/mortgage-workflow.md)). Proof: `python scripts/demo.py` and `pytest tests/test_mortgage_workflow.py`.

## 8. Patterns, single agents and the BFF

- The five orchestration patterns on the same facts ([components/orchestrations.md](components/orchestrations.md)).
- HR and IT single agents ([components/single-agents.md](components/single-agents.md)).
- The FastAPI BFF and the three container images ([components/bff-and-services.md](components/bff-and-services.md)).

## 9. Evals as a release gate

Golden sets, custom evaluators and `THRESHOLDS` ([components/evals.md](components/evals.md)). `python scripts/run_evals.py --out evals-out` exits 1 on regression and runs in CI.

## 10. Infrastructure and pipelines

Bicep modules and the Terraform twin, validated offline in CI; deploy and teardown workflows are gated ([components/infrastructure.md](components/infrastructure.md), [deployment.md](deployment.md)). Nothing has been deployed.

## 11. Keep the docs honest

`scripts/doc_drift.py` regenerates every `<!-- output: ... -->` and `<!-- code: ... -->` block in the Markdown files. CI runs `python scripts/doc_drift.py --check` and fails when pasted output or code excerpts no longer match the code. After changing code:

```bash
python scripts/doc_drift.py          # refresh blocks
python scripts/doc_drift.py --check  # what CI runs
```

## 12. Switching to Azure

Run `azd up` in a sandbox subscription (see [deploy.md](deploy.md)), then set `AAP_MODE=azure` with the azd outputs. The postprovision hook seeds AI Search, registers the Foundry agents and checks the agent cards. The Azure code paths follow the verified SDK signatures but have only run offline.
