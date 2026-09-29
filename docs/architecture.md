# Architecture

## Four planes

| Plane | Changes on | In this repo | Azure service |
|---|---|---|---|
| Experience | release train of the channels | `bff.py` (REST), which Teams / web / Copilot surfaces call | APIM (Consumption) → Container Apps (BFF) |
| Agent | weekly prompt/graph releases | MAF graph (`mortgage/workflow.py`), single agents, A2A agents (`a2a/`) | Container Apps + Foundry Agent Service + Foundry models |
| Knowledge | index refresh / policy effective dates | context builder, hybrid + semantic search with temporal + ACL filters, graph RAG, memory/checkpoints | Azure AI Search, Cosmos DB, Document Intelligence, Content Safety |
| Data | system-of-record change cadence | LOS, credit bureau, CRM/ERP behind MCP/A2A (synthetic) | Service Bus (queued writes); SoRs are external |

## Topology (deployed)

```
Internet ─► APIM (JWT, identity headers, rate limit, kill switch)
              └─► ca-bff  (external ingress; MI: orchestrator)
                    ├─ MAF graph in-process ── Foundry project (gpt-5-mini, text-embedding-3-small)
                    │                        ├─ AI Search (investor-guidelines, hr-policies)
                    │                        ├─ Document Intelligence (paystub / W-2 / bank statement)
                    │                        ├─ Content Safety (text + Prompt Shields)
                    │                        ├─ Cosmos DB serverless (checkpoints, memory, runs)
                    │                        └─ Service Bus (los-writes, agent-outbox)
                    ├─ A2A ─► ca-crm-agent / ca-erp-agent / ca-underwriting-agent   (internal ingress)
                    └─ MCP ─► ca-mcp-credit-bureau / ca-mcp-los                     (internal ingress; MI: tools)
```

* **Identity.** There are two user-assigned managed identities. *orchestrator* holds data-plane roles on the AI and data services. *tools* can only pull images and read Key Vault secrets. The per-user principal arrives from APIM as claims-derived headers and travels in the A2A metadata and the MAF state, so ACL filters apply per request.
* **Control plane.** The agent cards are published at `/.well-known/agent-card.json` (A2A 1.0), with a legacy alias at `/.well-known/agent.json`. `AgentDirectory` enforces `allowed_callers`, stage, the promotion gate, and the kill switch. The callee also re-checks authorization server-side. APIM's `agents-enabled` named value is the global kill switch.
* **Single vs multi-agent.** The HR policy and IT service desk agents are single agents: one prompt, a few tools, no graph. The mortgage flow is a graph because it needs parallel evidence gathering, deterministic stop conditions, a critic loop, checkpointed HITL, and queued writes with compensation.
* **Hand-built graph vs prebuilt orchestrations.** `orchestrations/` runs a lighter version of the same task (loan conditions review) through MAF's five prebuilt builders: sequential, concurrent, handoff, group chat and Magentic. It measures what each one costs in model calls and how it behaves under faults (see [orchestration-patterns.md](orchestration-patterns.md)). The flagship flow stays a hand-built `WorkflowBuilder` graph. It needs typed state, per-node five-exit handling, compensation and queued writes, and the prebuilt builders model none of these.
* **Foundry Agent Service vs MAF.** The HR agent exists both as a MAF agent (per-request ACL filter) and as a Foundry prompt agent with the `azure_ai_search` tool (static filter per version). `scripts/foundry_register.py` shows the trade-off in code.

## Request sequence (underwrite → approve)

See the mermaid diagram in the README. Its ten steps map to: edge (APIM), BFF session/run, intent (the explicit endpoint), graph routing (MAF), context builder, planner (the rules engine picks topics), tool execution (MCP/A2A), critic loop, human approval (`request_info`), then response + ops (letter, queued LOS write, outbox, traces).

## Orchestration patterns (prebuilt MAF builders)

| Pattern | Who decides the next step | Cost driver (offline, per loan) | Failure behaviour seen in drills |
|---|---|---|---|
| Sequential | Fixed order | One pass per agent, plus a human review of the final answer | A dead lane leads the underwriter to `refer`; a paused run survives a restart from a checkpoint |
| Concurrent | No one: parallel fan-out and deterministic fan-in | Cheapest, since there is no synthesizer call | The aggregator refers on a missing lane |
| Handoff | Each agent, via `handoff_to_*` tools | Only the lanes with findings are visited | An agent that does not hand off stops the run for a human |
| Group chat | `selection_func` or an orchestrator agent | Adds one reviewer turn, and one call per round for an LLM orchestrator | The checker supplied the dead lane's flag; an unapproved round cap leads to `refer` |
| Magentic | A manager LLM with task and progress ledgers | Most expensive (facts, plan, a ledger per round, final answer) | A stall causes reset + replan; the reset wipes history, so the manager must carry failures forward |

Measured numbers and the fault drills: [orchestration-patterns.md](orchestration-patterns.md).
