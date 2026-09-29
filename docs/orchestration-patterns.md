# Multi-agent orchestration patterns on MAF

`src/agentplatform/orchestrations/` runs one business task through each of Microsoft Agent Framework's
five prebuilt orchestration builders (package `agent-framework-orchestrations` 1.2.0, imported as
`agent_framework.orchestrations`). The task is a **loan conditions review**: given a loan id, decide which
underwriting conditions apply and whether the file can be approved, approved with conditions, or must be
referred.

The same cast is used by every pattern (`orchestrations/roles.py`):

| Role | Tools | Job |
|---|---|---|
| `triage` | `screen_loan` | Handoff only. Screens which lanes raise findings and routes to them. |
| `income`, `credit`, `assets` | `get_<lane>_facts` | Report findings and a `FLAGS:` line from deterministic facts. |
| `underwriter` | none | Merges `FLAGS:` lines (plus any `ADD:`/`MISSING:` from a human or reviewer) into `CONDITIONS:` + `DECISION:`. Refers if a lane answered without findings. |
| `reviewer` | `get_all_flags` | Group chat checker. Replies `APPROVED` or `MISSING: ...`. |

All facts come from the same data plane as the main underwriting graph (`orchestrations/facts.py`): the LOS
seed, Document Intelligence (offline fixtures), a tri-merge pull from the credit-bureau **MCP server through
the tool gateway**, and `mortgage/calculators.py`. The flag thresholds (`DTI_LIMIT = 0.45`, 2 months of
reserves, a 90-day inquiry lookback) are demo values for synthetic data, not a published guideline. The
answer key for scoring (`expected_flags`) is computed by the same deterministic rules.
The scenario is intentionally simpler than the flagship graph. It has no temporal guideline versions, no
reserves offset and no graph RAG. So L-1003 (DTI 48.3%) is **referred** here, while the flagship approves
it with conditions under the v2 rule in force on its application date.

## The five builders as used here

| Module | Builder and options used | Shape |
|---|---|---|
| `sequential.py` | `SequentialBuilder(participants, checkpoint_storage)` + `.with_request_info(agents=["underwriter"])` | income → credit → assets → underwriter, then a **human review of the underwriter's answer** (`AgentRequestInfoResponse.approve()` or `.from_strings([...])` feedback, which re-runs the underwriter). `restart=True` rebuilds the graph from the latest checkpoint while paused. |
| `concurrent.py` | `ConcurrentBuilder(participants)` + `.with_aggregator(callback)` | The three lanes fan out in parallel. A deterministic aggregator (no LLM) fans in and refers if any lane returned no `FLAGS:` line. |
| `handoff.py` | `HandoffBuilder(participants)` + `.with_start_agent` + `.add_handoff(src, targets)` + `.with_termination_condition` | Triage hands off only to lanes that have findings; each lane hands to the next lane or to the underwriter. Routing happens through the injected `handoff_to_<name>` tools. An agent that answers without handing off pauses the run with **`HandoffAgentUserRequest`** (for example, triage asking for a missing loan id). The run also has a hard cap of 12 agent turns. |
| `group_chat.py` | `GroupChatBuilder(participants, selection_func=… \| orchestrator_agent=…, max_rounds=9, termination_condition, output_from="all")` | Maker-checker: each lane speaks once, then underwriter and reviewer alternate until `APPROVED`. Two speaker-selection modes: a Python `selection_func(GroupChatState)`, or an LLM orchestrator agent returning `AgentOrchestrationOutput` JSON. If the round cap is reached without approval, the decision is forced to `refer`. |
| `magentic.py` | `MagenticBuilder(participants, manager_agent, enable_plan_review=True, max_round_count=10, max_stall_count=1, max_reset_count=2, checkpoint_storage, output_from="all")` | The manager (`StandardMagenticManager` wrapping an agent) writes a task ledger and a plan, **which a human approves or revises** (`MagenticPlanReviewRequest.approve()/.revise()`). It then writes a JSON progress ledger every round. A stall triggers reset + replan; round and reset caps end the run. |

Every run is wrapped in an `orchestration.run` OpenTelemetry span (`harness/tracing.py`), and each human
answer gets an `orchestration.hitl` span. The fact pull emits `orchestration.facts` plus the gateway's
`tool.call` span.

## Measured comparison (offline, deterministic mock model)

Regenerate with `python scripts/orchestrations_demo.py --compare --write`. `tests/test_orchestrations.py`
fails if this block is stale.

**How to read it.** Offline, every agent runs on the repo's `MockChatClient` with a small script that
behaves like a well-instructed model. So these numbers measure **orchestration overhead and control flow**:
how many model calls and turns each builder spends, and what it does when something breaks. They do not
measure model quality. All patterns reach the rule answer on all three loans because the scripted agents
don't make mistakes. The gaps you should expect with a real model (such as a lane skipped or a flag
dropped) are what the drills below exercise. Tokens and latency are left out because the mock has neither.
"LLM calls" counts every chat-client call, including tool-calling round trips and orchestrator/manager calls.

<!-- comparison:start -->
| Pattern | Exact conditions + decision (3 loans) | Flag recall | LLM calls / loan | Agent turns / loan | HITL pauses / loan | Decisions (L-1001, L-1002, L-1003) |
|---|---|---|---|---|---|---|
| sequential | 3/3 | 1.00 | 7.0 | 4.0 | 1.0 | approve_with_conditions, refer, refer |
| concurrent | 3/3 | 1.00 | 6.0 | 3.0 | 0.0 | approve_with_conditions, refer, refer |
| handoff | 3/3 | 1.00 | 6.3 | 3.7 | 0.0 | approve_with_conditions, refer, refer |
| group_chat (selection_func) | 3/3 | 1.00 | 9.0 | 5.0 | 0.0 | approve_with_conditions, refer, refer |
| group_chat (orchestrator_agent) | 3/3 | 1.00 | 14.0 | 5.0 | 0.0 | approve_with_conditions, refer, refer |
| magentic | 3/3 | 1.00 | 15.0 | 4.0 | 1.0 | approve_with_conditions, refer, refer |

| Pattern | Drill | Decision | Stop reason | LLM calls | HITL pauses |
|---|---|---|---|---|---|
| sequential | assets analyst down (L-1001) | refer | completed | 6 | 1 |
| concurrent | assets analyst down (L-1001) | refer | missing_lanes | 5 | 0 |
| handoff | assets analyst down (L-1001) | none | awaiting_user | 7 | 2 |
| group_chat (selection_func) | assets analyst down (L-1001) | refer | approved | 10 | 0 |
| magentic | assets analyst down (L-1001) | refer | completed | 23 | 2 |
| group_chat (selection_func) | reviewer never approves (L-1001) | refer | max_rounds_unapproved | 13 | 0 |
| handoff | request has no loan id (L-1002) | refer | completed | 8 | 1 |
| magentic | max_round_count=2 (L-1001) | refer | limit_reached | 8 | 1 |
| sequential | process restart while paused (L-1003) | refer | completed | 7 | 1 |
<!-- comparison:end -->

## What the numbers say

* **Concurrent is the cheapest complete review.** It uses 6 calls per loan and no synthesizer call, because
  the fan-in is deterministic code. It is the right shape when the lanes are independent and the merge
  is a rule.
* **Handoff spends calls only where there are findings.** Triage costs 2 calls but skips clean lanes: 5
  calls on L-1003 (credit only) and 7 on L-1001 and L-1002 (two lanes each), against sequential's flat 7. The price is that the route rests
  on the triage decision, and a specialist that answers without handing off stops the run for a human
  (the `assets analyst down` drill shows this: no decision, pending with the user).
* **Group chat buys a checker.** The reviewer turn costs 2 calls per loan over sequential without HITL.
  In the `assets analyst down` drill it was the only pattern that still produced the full condition list:
  the reviewer's `MISSING:` supplied the flag the dead lane never reported, and the decision still went to
  `refer`. The LLM orchestrator adds exactly one call per round over `selection_func` for the same result,
  so use a Python selector when the turn order is known.
* **Magentic is the most expensive** (15 calls per loan here: facts, plan, 5 progress ledgers and the final
  answer on top of the workers). But it is the only pattern that notices a stalled worker, resets and
  replans on its own. **The reset clears the chat history.** Evidence that a lane failed is lost unless the
  manager carries it forward, so `ManagerScript` puts `MISSING_LANES:` into the underwriter's instruction.
  Without that, the first version of this code approved L-1001 with the assets lane missing. Plan review
  fires again after a reset.
* **Sequential with `with_request_info`** is the simplest auditable HITL: the human sees the full
  conversation in the `AgentExecutorResponse` payload, and a checkpointed pause survives a process restart.

## Choosing

| Need | Pattern |
|---|---|
| Independent evidence lanes, rule-based merge | Concurrent + custom aggregator |
| Fixed order, human signs the final answer | Sequential + `with_request_info` |
| Route by content, skip irrelevant specialists, ask the user when stuck | Handoff |
| Maker-checker / debate with a bounded number of rounds | Group chat (`selection_func` if the order is known) |
| Open-ended task, dynamic plan, recover from stalls, human approves the plan | Magentic |

The flagship underwriting flow (`mortgage/workflow.py`) remains a hand-built `WorkflowBuilder` graph. It
needs typed state, per-node five-exit failure handling, compensation and queued writes, which the prebuilt
builders don't model.
