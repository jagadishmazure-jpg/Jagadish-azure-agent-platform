# `orchestrations/`: MAF's five prebuilt multi-agent patterns

One business task, a **loan conditions review** (which underwriting conditions apply, and whether to
approve, approve with conditions, or refer), run through each builder in `agent_framework.orchestrations`
(package `agent-framework-orchestrations` 1.2.0). The facts come from the same data plane as the flagship
graph: the LOS seed, Document Intelligence fixtures, the credit-bureau MCP server via the tool gateway,
and the calculators. Agents read them through tools and never compute numbers themselves.

Offline, every agent is a real MAF `Agent` on `MockChatClient`, with a small deterministic script. With
`AAP_MODE=azure`, the same agents use `get_chat_client()` (Foundry), and their instructions define the
output format. The measured comparison, fault drills and trade-offs are in
[`docs/orchestration-patterns.md`](../../../docs/orchestration-patterns.md).

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`facts.py`](facts.py) | `gather_facts(loan_id)` builds the deterministic fact sheet (income, tri-merge credit via MCP, DTI, assets, reserves) and per-lane flags. `expected_flags()` is the answer key. The thresholds are demo values. |
| [`roles.py`](roles.py) | The cast: triage, income/credit/assets analysts, underwriter, reviewer. Holds their instructions, the facts tools (`get_<lane>_facts`, `get_all_flags`, `screen_loan`), the offline scripts (including chaos: `assets_down`, `looping_reviewer`), and a `Roster` that builds agents and counts model calls. |
| [`base.py`](base.py) | `OrchestrationRun` result (conditions, decision, recall, exact match, turns, HITL requests, stop reason) and output helpers. |
| [`hitl.py`](hitl.py) | `drive()`: answers pending `request_info` events with a responder until the workflow is idle, up to a bounded number of pauses, each in an `orchestration.hitl` span. |
| [`sequential.py`](sequential.py) | `SequentialBuilder` + `.with_request_info(agents=["underwriter"])` + checkpoint storage. A human approves or sends feedback on the underwriter's answer; `restart=True` resumes from the latest checkpoint in a fresh graph. |
| [`concurrent.py`](concurrent.py) | `ConcurrentBuilder` + `.with_aggregator(callback)`. The lanes run in parallel and a deterministic fan-in refers when a lane has no findings. |
| [`handoff.py`](handoff.py) | `HandoffBuilder` + `.with_start_agent` / `.add_handoff` / `.with_termination_condition`. Triage routes only to lanes with findings via `handoff_to_<name>` tools. A missing loan id surfaces as `HandoffAgentUserRequest`. |
| [`group_chat.py`](group_chat.py) | `GroupChatBuilder`, maker-checker (underwriter ⇄ reviewer), using either `selection_func` or an LLM `orchestrator_agent` (`AgentOrchestrationOutput` JSON), with `max_rounds` and a termination condition. An unapproved cap becomes `refer`. |
| [`magentic.py`](magentic.py) | `MagenticBuilder` with `manager_agent` (wrapped in `StandardMagenticManager`), plan review HITL, stall/reset/round caps and checkpointing. `ManagerScript` answers the manager's facts/plan/progress-ledger/final prompts offline and carries failed lanes across resets. |
| [`compare.py`](compare.py) | Runs every pattern over L-1001..L-1003 plus the fault drills, and renders the comparison block for the docs page. |

```bash
python scripts/orchestrations_demo.py                     # transcripts, one per pattern
python scripts/orchestrations_demo.py --compare --write   # refresh docs/orchestration-patterns.md
pytest tests/test_orchestrations.py -q                    # 36 tests
```
