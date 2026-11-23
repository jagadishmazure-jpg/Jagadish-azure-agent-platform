# `durable_agents/`: Durable Task replay (offline)

An offline checkpoint-and-resume runtime for a multi-agent loan review. It follows the
Durable Task rule from Microsoft Learn: when the process starts again, **completed model
calls are read from history and are not executed**. A durable wait parks the run until an
underwriter approves or sends it back. No Durable Task Scheduler and no Azure Functions
host are required.

The Learn import paths (`AgentFunctionApp`, `DurableAIAgentWorker`) are not in the pinned
packages. They are marked `[verify]` on the runtime.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Public exports. |
| [`runtime.py`](runtime.py) | JSON history, replay, external events, crash-before-checkpoint hook. |
| [`loan.py`](loan.py) | Intake, credit, underwriter wait, letter, idempotent publish. |

```bash
python scripts/component_demos.py durable_agents
pytest tests/test_durable_agents.py -q
```

Design notes: [docs/components/durable-agents.md](../../../docs/components/durable-agents.md).
