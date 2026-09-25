import pytest
from mcp import Client

from agentplatform.harness.budgets import Budget, BudgetExceeded
from agentplatform.harness.resilience import TransientError
from agentplatform.mcp_servers import credit_bureau, los
from agentplatform.mcp_servers.gateway import ToolError, ToolGateway


async def test_mcp_tool_surface_is_small_and_read_only():
    async with Client(credit_bureau.server) as c:
        names = sorted(t.name for t in (await c.list_tools()).tools)
    assert names == ["get_report", "pull_tri_merge"]
    async with Client(los.server) as c:
        names = sorted(t.name for t in (await c.list_tools()).tools)
    assert names == ["get_loan_file", "queue_status_update"]


async def test_gateway_idempotent_pull_and_transient_mapping():
    gw = ToolGateway()
    a = await gw.call("credit-bureau", "pull_tri_merge", {"borrower_id": "B-1002", "request_id": "t-1"})
    b = await gw.call("credit-bureau", "pull_tri_merge", {"borrower_id": "B-1002", "request_id": "t-1"})
    assert a == b and a["representative_score"] == 701
    credit_bureau.STATS["fail_next"] = 1
    with pytest.raises(TransientError):
        await gw.call("credit-bureau", "pull_tri_merge", {"borrower_id": "B-1002", "request_id": "t-2"})


async def test_gateway_budget_and_errors():
    gw = ToolGateway(Budget(max_identical_calls=1))
    await gw.call("los", "get_loan_file", {"loan_id": "L-1001"})
    with pytest.raises(BudgetExceeded):
        await gw.call("los", "get_loan_file", {"loan_id": "L-1001"})
    with pytest.raises(ToolError):
        await ToolGateway().call("los", "get_loan_file", {"loan_id": "nope"})


async def test_los_queue_is_idempotent():
    gw = ToolGateway()
    args = {"loan_id": "L-1001", "status": "in_review", "idempotency_key": "k-1"}
    t1 = await gw.call("los", "queue_status_update", args, write=True)
    t2 = await ToolGateway().call("los", "queue_status_update", args, write=True)
    assert t1 == t2


async def test_unreachable_mcp_server_maps_to_transient(monkeypatch):
    """A down MCP endpoint must enter the failure policy as TransientError (retry/degrade), not crash the graph."""
    from agentplatform.harness.resilience import TransientError
    from agentplatform.mcp_servers.gateway import ToolGateway

    monkeypatch.setenv("MCP_LOS_URL", "http://127.0.0.1:9/mcp")
    with pytest.raises(TransientError):
        await ToolGateway().call("los", "get_loan_file", {"loan_id": "L-1001"})
