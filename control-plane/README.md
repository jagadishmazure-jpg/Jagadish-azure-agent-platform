# `control-plane/`: agent directory artefacts

Checked-in, generated contracts for agent-to-agent calls.

| Folder | What it holds |
|---|---|
| [`agent-cards/`](agent-cards/README.md) | A2A agent cards (one JSON per agent) and `_policy.json`, generated from `src/agentplatform/a2a/catalog.py` by `scripts/export_agent_cards.py`. CI runs `--check` so the cards cannot drift from the catalog. |

See [docs/components/a2a-control-plane.md](../docs/components/a2a-control-plane.md).
