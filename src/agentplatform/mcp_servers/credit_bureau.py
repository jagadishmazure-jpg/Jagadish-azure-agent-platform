"""Mock tri-merge credit bureau as an MCP server (read-only, idempotent by request_id).

Small tool surface on purpose: `pull_tri_merge` and `get_report`. No `run_any_query`."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from agentplatform.mcp_servers._data import seed

server = MCPServer(
    "credit-bureau",
    instructions="Mock tri-merge credit bureau. Read-only. Requires permissible purpose and borrower consent.",
)
_reports: dict[str, dict] = {}
STATS = {"hard_pulls": 0, "fail_next": 0}


@server.tool()
def pull_tri_merge(
    borrower_id: str, request_id: str, permissible_purpose: str = "mortgage_origination"
) -> dict:
    """Pull a tri-merge credit report. Re-using request_id returns the same report (no second hard pull)."""
    if STATS["fail_next"] > 0:
        STATS["fail_next"] -= 1
        raise ToolError("TRANSIENT bureau timeout (simulated)")
    if request_id in _reports:
        return _reports[request_id]
    if permissible_purpose != "mortgage_origination":
        raise ToolError("permissible purpose not allowed")
    data = seed()
    if "credit_pull" not in data["crm"].get(borrower_id, {}).get("consents", []):
        raise ToolError("no credit-pull consent on file")
    rec = data["credit"][borrower_id]
    scores = sorted(rec["scores"].values())
    report = {
        "request_id": request_id,
        "report_id": f"CR-{borrower_id}-{rec['report_date']}",
        "borrower_id": borrower_id,
        "report_date": rec["report_date"],
        "scores": rec["scores"],
        "representative_score": scores[1],
        "monthly_liabilities": sum(t["monthly_payment"] for t in rec["tradelines"]),
        "tradelines": rec["tradelines"],
        "inquiries": rec["inquiries"],
        "public_records": rec["public_records"],
    }
    STATS["hard_pulls"] += 1
    _reports[request_id] = report
    return report


@server.tool()
def get_report(request_id: str) -> dict:
    """Fetch a previously pulled report by request id."""
    return _reports.get(request_id, {"error": "not_found"})
