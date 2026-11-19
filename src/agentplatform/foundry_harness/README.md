# `foundry_harness/`: Copilot harness and Toolbox (offline)

A Foundry hosted-agent sample that stays offline. The **Microsoft Copilot harness** mock owns
the agent loop and the sandbox. The sample supplies a skill, guideline knowledge and a
**Toolbox** whose tools are shared through one managed MCP endpoint. A loan-commitment
workflow pauses for a named human before `queue_commitment`.

Preview shapes that are not in the pinned SDKs are marked `[verify]`. Nothing here calls Foundry.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Public exports. |
| [`models.py`](models.py) | Skill, knowledge, tool, sandbox, model-action and run types. |
| [`toolbox.py`](toolbox.py) | Versioned toolbox, consumer and developer MCP URLs, `tools/list` and `tools/call`. |
| [`harness.py`](harness.py) | `CopilotHarness`: loop, sandbox, as-of knowledge filter, approval gate. |
| [`loan.py`](loan.py) | Synthetic applications, DTI rule, toolbox build, and `start_loan_review`. |
| [`skills/`](skills/README.md) | `underwrite-file` procedure (`SKILL.md`). |
| [`definitions/`](definitions/README.md) | Source-controlled prompt-agent definition (`microsoft_copilot_preview`). |

```bash
python scripts/component_demos.py foundry_harness
pytest tests/test_foundry_harness.py -q
```

Design notes: [docs/components/foundry-harness.md](../../../docs/components/foundry-harness.md).
