# `scripts/`: demo, eval, codegen and deployment helpers

Command-line entry points that sit outside the package: the offline demo, the eval release
gate, generators for checked-in artefacts (agent cards, failure table), a Docker-free local
mesh, and the azd post-provision steps (search index seeding and Foundry agent registration).
The Azure-facing scripts have `--dry-run` modes that run fully offline.

| File | What it does |
|---|---|
| [`demo.py`](demo.py) | Offline end-to-end demo: underwrites L-1001, L-1002 and L-1003, approves at the HITL gate and prints the letters (`make demo`). |
| [`export_agent_cards.py`](export_agent_cards.py) | Writes `control-plane/agent-cards/*.json` and `_policy.json` from the catalog; `--check` exits 1 if any checked-in card is stale (`make cards`, CI). |
| [`foundry_register.py`](foundry_register.py) | Registers the single agents in Foundry Agent Service (azure-ai-projects 2.x). `--dry-run` (default) prints definitions offline; `--apply` creates a new version of each agent; `--invoke <agent> "question"` calls one. Needs `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_SEARCH_CONNECTION` and the Azure AI User role for non-dry runs. |
| [`orchestrations_demo.py`](orchestrations_demo.py) | Offline transcripts of the five MAF orchestration patterns (`--loan`, `--pattern`). `--compare` prints the pattern comparison and fault drills, `--write` refreshes `docs/orchestration-patterns.md`, and `--check` exits 1 if that doc is stale. |
| [`postprovision.sh`](postprovision.sh) | azd `postprovision` hook: sets `AAP_MODE=azure`, installs the `eval` extra, seeds AI Search, registers Foundry agents and runs the eval gate. |
| [`render_docs.py`](render_docs.py) | Regenerates `docs/failure-table.md` from `FAILURE_TABLE` (single source of truth). |
| [`run_evals.py`](run_evals.py) | Golden-set evals and release gate (`make evals`): offline deterministic evaluators by default, exit 1 on regression; `--azure` also scores with azure-ai-evaluation and logs to the Foundry project; `--out DIR` writes eval rows. |
| [`run_local_mesh.sh`](run_local_mesh.sh) | Docker-free equivalent of docker-compose (`make mesh`): starts the two MCP servers (ports 9101-9102), CRM/ERP/underwriting A2A agents (9201-9203) and the BFF (8080) as separate processes over HTTP. |
| [`seed_search_index.py`](seed_search_index.py) | Creates or refreshes the investor-guideline and HR-policy indexes and uploads the synthetic corpora with embeddings; `--dry-run` prints the index JSON and first document offline. |

## Offline commands (verified)

```bash
python scripts/demo.py
python scripts/orchestrations_demo.py --compare --check
python scripts/run_evals.py --out evals-out
python scripts/export_agent_cards.py --check
python scripts/render_docs.py
python scripts/foundry_register.py --dry-run
python scripts/seed_search_index.py --dry-run
./scripts/run_local_mesh.sh        # then: curl -X POST localhost:8080/loans/L-1001/underwrite
```

`--apply`, `--invoke`, `--azure` and the non-dry-run seeding need real Azure resources and have
not been run.
