# `a2a/`: A2A agent fabric and control plane

Everything needed for agents to call each other over the A2A 1.0 protocol (a2a-sdk 1.x):
a catalog of first-party domain agents (CRM, ERP, underwriting) and clearly labelled vendor
**stand-ins**, card generation with a control-plane extension, a directory that decides
who-may-call-whom and gates promotion, a server factory that re-checks policy on every inbound
task, and a client that propagates `traceparent` and tenant and validates foreign output.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`__main__.py`](__main__.py) | Serves one agent over HTTP: `python -m agentplatform.a2a crm-agent` (or `AGENT_ID` env; port from `PORT` or the catalog). Used by `services/a2a/Dockerfile` and `scripts/run_local_mesh.sh`. |
| [`agents.py`](agents.py) | Skill handlers (`HANDLERS`) for `crm_agent`, `erp_agent`, `underwriting_agent` and the stand-ins; `underwriting_service()` returns the shared `UnderwritingService` used by the BFF too. |
| [`cards.py`](cards.py) | `SkillSpec`, `AgentSpec`, `to_agent_card` and `card_json`: one card contract for first-party agents and stand-ins, with control-plane metadata in an `AgentExtension`. |
| [`catalog.py`](catalog.py) | `CATALOG` and `spec_by_id`: `underwriting-agent`, `crm-agent`, `erp-agent`, `dynamics-crm-standin`, `salesforce-crm-standin`, `sap-erp-standin`. Stand-ins imitate the shape of vendor agents and make no vendor API calls. |
| [`client.py`](client.py) | `A2AClient.send`: directory policy check, kill switch, JSON-RPC `SendMessage` with `traceparent` and tenant headers, then schema validation of the returned artifact; `A2AError` on refusal. |
| [`local.py`](local.py) | In-process mesh for offline runs and tests: every agent's real A2A app mounted behind an httpx ASGI transport (`local_apps`, `local_client`, `crm_lookup_via_a2a`). In Container Apps the same client uses `A2A_<AGENT>_URL`. |
| [`registry.py`](registry.py) | `AgentDirectory` (`DIRECTORY`): `authorize(caller, callee, tenant, skill)`, `register` (promotion gate: production requires eval score >= `PROMOTION_MIN_EVAL` = 0.85), `kill` / `revive`, `cards`. `PolicyDecision` carries the reason. |
| [`server.py`](server.py) | `create_a2a_app(spec, handler)`: checks tenant and caller headers, authorizes against the directory (defence in depth behind APIM), checks the kill switch and traces with the caller's traceparent. `DomainAgentExecutor`, `CallContext`. |

## Run one agent

```bash
python -m agentplatform.a2a crm-agent                 # serves the card and JSON-RPC endpoint
curl localhost:8102/.well-known/agent-card.json        # default port for crm-agent from the catalog
```

(`scripts/run_local_mesh.sh` overrides ports with `PORT`, e.g. 9201 for `crm-agent`.)

## Design notes

- Policy is enforced twice: by the client before the network call, and by the callee's server.
- Write skills with human-in-the-loop (`write-hitl`) require `approved_by`, and writes are
  idempotent (see `tests/test_a2a.py`).
- The checked-in cards in [`control-plane/agent-cards`](../../../control-plane/agent-cards/README.md)
  are generated from `catalog.py`.

Tests: `pytest tests/test_a2a.py` (10 tests).
