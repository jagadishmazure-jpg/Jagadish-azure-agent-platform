# `single/`: single-agent examples

Two deliberately simple agents that contrast with the multi-agent mortgage graph: one agent,
one prompt, a few tools, no graph. That is the right shape for bounded Q&A or triage with at
most one human-approved write. Each runs offline as a MAF agent, and each has a Foundry Agent
Service definition registered by `scripts/foundry_register.py` (dry-run offline).

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`hr_agent.py`](hr_agent.py) | HR policy agent: `build_hr_agent`, `make_search_tool` (temporal + ACL filtering applied in the tool as a Search filter, not by the model) and `ask_hr` returning a cited `PolicyAnswer`. |
| [`it_agent.py`](it_agent.py) | IT service desk agent: `build_it_agent` with a read tool, a queued-write tool and an approval-gated password-reset tool (`approval_mode="always_require"`); `run_it` surfaces approval requests; `ITDesk` records side effects. |

```bash
curl -X POST localhost:8080/chat/hr -H 'content-type: application/json' \
  -d '{"message": "How many weeks of parental leave?"}'
pytest tests/test_single_agents.py
```
