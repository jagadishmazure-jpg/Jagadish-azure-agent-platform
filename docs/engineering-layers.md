# Engineering layers → code

Each layer can be changed, tested, and versioned on its own. The table points to where each one lives in this repo.

| Layer | What it owns | Where | How it's tested |
|---|---|---|---|
| **Prompt** | Versioned prompt pack (id, semver, owner, risk tier), bound to Pydantic output schemas. Agents and cards pin `prompt_ref` + sha. | `prompts/pack/*.md`, `prompts/registry.py`, `prompts/schemas.py` | schema validation in every agent call; eval gate |
| **Context** | Context builder: ACL + as-of temporal re-check, injection screen, per-kind token budgets, PII redaction, source map, known-policy cache for degrade. | `context/builder.py`, `context/sanitize.py`, `knowledge/search.py` (hybrid + semantic + OData security filter), `knowledge/graph.py` (graph RAG) | `test_knowledge.py` |
| **Workflow** | Deterministic MAF graph: fan-out/fan-in, switch-case routing, checkpoints (File/Cosmos), HITL `request_info`, stop conditions (`max_iterations`, max repairs, budgets). | `mortgage/workflow.py`, `mortgage/service.py` | `test_mortgage_workflow.py` |
| **Agent** | MAF `Agent`s with one job each (intake/income/assets/credit narrative, conditions, letter). Numbers come from tools and calculators, never from the model. Single agents: HR policy, IT service desk. | `mortgage/agents.py`, `single/*.py`, `llm/clients.py` | `test_single_agents.py` |
| **Graph** | Knowledge graph over borrower / property / counterparties for related-party and non-arm's-length detection. | `knowledge/graph.py` | `test_graph_rag_detects_non_arms_length` |
| **Loop** | Critic/evaluator loop: every condition must cite a guideline that is in the evidence and in force; one bounded repair pass, then drop + escalate. Offline evals are the promotion gate. | `mortgage/critic.py`, `evals/*` | `test_critic_*`, `test_evals.py` |
| **Harness** | Identity envelope (principal, tenant, traceparent), budgets (steps/tokens/tool calls/identical-call caps), kill switch, retries + circuit breaker, five-exit failure policy, outbox, OpenTelemetry. | `harness/*` | `test_harness.py` |
| **Platform** | Tool plane (MCP servers behind a gateway), agent control plane (A2A cards, directory, who-can-call-whom, promotion gate), BFF, Foundry agent registration, content safety, Bicep/azd, CI. | `mcp_servers/*`, `a2a/*`, `bff.py`, `safety/*`, `scripts/*`, `infra/*`, `.github/workflows/*` | `test_mcp.py`, `test_a2a.py`, `test_bff.py`, `test_infra.py` |

## Ops loops (MLOps + LLMOps + AgentOps)

* **MLOps**: the deterministic calculators and rule parameters (DTI max, score floors) are versioned *data* in the guideline index (`params_json`). No trained model ships in this repo. A bureau score or fraud model would plug in as an MCP tool with its own model registry.
* **LLMOps**: prompt pack semver, embedding and index schema (`knowledge/index_schema.py`), golden sets, groundedness/relevance via `azure-ai-evaluation`, content safety on inbound and retrieved text.
* **AgentOps**: agent cards with owner, stage, eval score, and allowed callers (`control-plane/agent-cards/`); the promotion gate refuses registration below 0.85; APIM plus the directory each have a kill switch; every A2A hop carries `traceparent` + tenant; the five-exit table lives next to the graph.
