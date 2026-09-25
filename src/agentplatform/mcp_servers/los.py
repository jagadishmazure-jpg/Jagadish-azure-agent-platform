"""Loan origination system (LOS) as an MCP server: read the loan file; queue status updates.

Writes are *queued* (idempotency key required) — the LOS is the system of record, the agent is not."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from agentplatform.mcp_servers._data import seed

server = MCPServer("los", instructions="Loan origination system. Read loan files; queue status updates only.")
QUEUED: dict[str, dict] = {}


@server.tool()
def get_loan_file(loan_id: str) -> dict:
    """Return the LOS loan file (terms, parties, document manifest)."""
    loans = seed()["loans"]
    if loan_id not in loans:
        return {"error": "not_found", "loan_id": loan_id}
    return loans[loan_id]


@server.tool()
def queue_status_update(loan_id: str, status: str, idempotency_key: str) -> dict:
    """Queue an LOS status change. Same idempotency_key -> same ticket (no double post)."""
    if status not in {"conditionally_approved", "suspended", "in_review"}:
        return {"error": "status_not_allowed", "status": status}
    if idempotency_key not in QUEUED:
        QUEUED[idempotency_key] = {
            "ticket": f"LOS-Q-{len(QUEUED) + 1:04d}",
            "loan_id": loan_id,
            "status": status,
        }
    return QUEUED[idempotency_key]
