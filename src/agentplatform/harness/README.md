# `harness/`: everything that wraps an agent invocation

The harness layer: what surrounds each node or agent call but is neither the prompt nor the
model. It carries identity and trace context, enforces stop conditions, honours kill switches,
retries transient failures behind circuit breakers, maps every failure to one of five exits,
queues writes through an outbox and emits OpenTelemetry spans.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`budgets.py`](budgets.py) | `Budget` and `BudgetExceeded`: max steps, max tool calls, max identical calls, a cost cap and max writes per run. |
| [`failure.py`](failure.py) | Five-exit handling: `Exit`, `NodeOutcome`, `FailurePolicy`, `run_with_exits` and `FAILURE_TABLE` (data read by the graph, the tests and `scripts/render_docs.py`). |
| [`identity.py`](identity.py) | `Principal` (user, tenant, groups, workload `agent_id`), `new_traceparent`, `child_traceparent` (same trace id, new span id per hop) and `trace_id_of`. |
| [`killswitch.py`](killswitch.py) | `KillSwitch` (`KILL_SWITCH`): global, per-agent and per-tenant `trip` / `reset` / `check`. The graph checks it between nodes; APIM enforces the same flag at the edge. |
| [`outbox.py`](outbox.py) | Queued writes with idempotency keys: `InMemoryOutbox` offline (with a chaos hook), `ServiceBusOutbox` on Azure (`message_id` = idempotency key), `get_outbox()`. |
| [`resilience.py`](resilience.py) | `retry_async` (jittered backoff; returns retries used), `CircuitBreaker`, `CircuitOpen` and `TransientError` (429 / 5xx / timeout). |
| [`tracing.py`](tracing.py) | `configure_tracing()` (Azure Monitor when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, console when `AAP_TRACE_CONSOLE=1`) and `span()` with tenant, thread, node, tool, token, cost and identity attributes. |

The rendered five-exit table is in [`docs/failure-table.md`](../../../docs/failure-table.md).

Tests: `pytest tests/test_harness.py` (budgets, traceparent, kill-switch scopes, five exits,
circuit breaker, failure-table completeness).
