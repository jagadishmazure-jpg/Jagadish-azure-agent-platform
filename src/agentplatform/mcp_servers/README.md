# `mcp_servers/`: MCP tool plane

Model Context Protocol servers (mcp 2.x) that wrap systems of record, and the gateway agents
use to reach them. The tool surfaces are deliberately small: the credit bureau exposes
`pull_tri_merge` and `get_report`; the loan origination system (LOS) exposes `get_loan_file` and
a queued, idempotent `queue_status_update`. Servers run over streamable HTTP at `/mcp`.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`__main__.py`](__main__.py) | `python -m agentplatform.mcp_servers credit-bureau|los` (or `MCP_SERVER` env) serves one server on `PORT` (default 8080). Used by `services/mcp/Dockerfile` and the local mesh. |
| [`_data.py`](_data.py) | `seed()`: loads the synthetic LOS, credit and CRM records from `mortgage/data/loans.json` (cached). |
| [`credit_bureau.py`](credit_bureau.py) | Mock tri-merge bureau: `pull_tri_merge` (reusing a `request_id` returns the same report, so no second hard pull) and `get_report`. |
| [`gateway.py`](gateway.py) | `ToolGateway.call`: budgets, circuit breakers, tracing and schema validation of results; an unreachable server maps to `TransientError` so the failure policy can retry or degrade. `ToolError` for other failures. |
| [`los.py`](los.py) | LOS server: `get_loan_file` (terms, parties, document manifest) and `queue_status_update` (same idempotency key, same ticket). |

## Run

```bash
PORT=9101 python -m agentplatform.mcp_servers credit-bureau   # http://127.0.0.1:9101/mcp
pytest tests/test_mcp.py
```
