# `src/agentplatform/`: the platform package

The installable Python package (`pip install -e .`). It holds the mortgage underwriting
flagship on Microsoft Agent Framework (MAF), the A2A control plane, the MCP tool servers, the
single-agent examples and every cross-cutting layer they share: prompts, context, knowledge,
document intelligence, safety, model clients, harness (identity, budgets, kill switch,
resilience, outbox, tracing) and evals. Everything runs offline against deterministic mocks by
default; `AAP_MODE=azure` swaps each adapter for its Azure service, in one place (`config.py`).

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`bff.py`](bff.py) | Experience-plane FastAPI app (`agentplatform.bff:app`). Reads identity from `x-user`, `x-tenant-id`, `x-groups` headers (set by APIM from the Entra token in Azure; demo defaults offline), screens inbound text with Content Safety and propagates `traceparent`. Routes: `GET /healthz`, `POST /loans/{loan_id}/underwrite` (group `loan-officers`), `GET /runs/{run_id}`, `POST /runs/{run_id}/decision` (group `underwriting`), `GET /directory`, `POST /directory/{agent_id}/kill` and `/revive` (group `platform-admins`), `POST /chat/hr`, `POST /chat/it`. |
| [`config.py`](config.py) | `Settings.from_env()` / `get_settings()`: the single mapping from env vars (azd outputs) to adapters, e.g. `AAP_MODE`, `AAP_TENANT_ID`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, `AZURE_SEARCH_ENDPOINT`, `AZURE_COSMOS_ENDPOINT`, `APPLICATIONINSIGHTS_CONNECTION_STRING`, `AAP_CHECKPOINT_DIR`. `azure_credential()` returns a managed identity in Container Apps and developer credentials locally. |
| [`a2a/`](a2a/README.md) | A2A 1.0 fabric: agent catalog and cards, directory policy, server factory, client, local mesh. |
| [`context/`](context/README.md) | The context builder every agent uses: retrieve, trim, screen, pack, cite. |
| [`docintel/`](docintel/README.md) | Document Intelligence prebuilt models for paystubs, W-2s and bank statements (offline fixtures). |
| [`evals/`](evals/README.md) | Golden sets, custom evaluators and the gated eval runner. |
| [`harness/`](harness/README.md) | Identity, budgets, kill switch, resilience, five-exit failure policy, outbox, tracing. |
| [`knowledge/`](knowledge/README.md) | Temporal + ACL hybrid search (AI Search or in-memory) and graph RAG. |
| [`llm/`](llm/README.md) | Chat clients: deterministic MAF mock offline, Foundry with fallback deployment on Azure. |
| [`mcp_servers/`](mcp_servers/README.md) | Credit bureau and LOS MCP servers plus the tool gateway. |
| [`mortgage/`](mortgage/README.md) | The flagship MAF workflow for mortgage underwriting conditions. |
| [`orchestrations/`](orchestrations/README.md) | MAF's five prebuilt multi-agent orchestrations (sequential, concurrent, handoff, group chat, Magentic) on a loan conditions review, with a measured comparison. |
| [`prompts/`](prompts/README.md) | Versioned prompt pack bound to output schemas. |
| [`safety/`](safety/README.md) | Content Safety and Prompt Shields gate. |
| [`single/`](single/README.md) | Single-agent examples: HR policy and IT service desk. |

## Layering

```
bff.py (experience) ──> mortgage/ (MAF graph) ──> llm/ · prompts/ · context/ ──> knowledge/ · docintel/
        │                     │                                     └──> safety/
        │                     ├──> mcp_servers/ (credit bureau, LOS) via ToolGateway
        │                     └──> a2a/ (CRM / ERP agents) via A2AClient + directory policy
        └──> single/ (HR, IT agents)
harness/ wraps every node: identity + traceparent, budgets, kill switch, retry/breaker, five exits, outbox, OTel
```

## Run

```bash
uvicorn agentplatform.bff:app --port 8080       # in-process BFF (offline mocks)
curl -X POST localhost:8080/loans/L-1001/underwrite
pytest -q                                       # 113 offline tests
```
