"""Tool gateway: the one path from agents to MCP servers — budgets, circuit breakers, tracing,
and schema validation of results (tool output is untrusted until validated)."""

from __future__ import annotations

import json
import os
from typing import Any

from mcp import Client
from pydantic import BaseModel

from agentplatform.harness.budgets import Budget
from agentplatform.harness.resilience import CircuitBreaker, TransientError
from agentplatform.harness.tracing import span


class ToolError(RuntimeError):
    pass


def _server_target(name: str):
    """Azure / compose: streamable HTTP URL from env (MCP_<NAME>_URL). Offline: in-process server."""
    url = os.environ.get(f"MCP_{name.upper().replace('-', '_')}_URL")
    if url:
        return url
    if name == "credit-bureau":
        from agentplatform.mcp_servers.credit_bureau import server
    elif name == "los":
        from agentplatform.mcp_servers.los import server
    else:
        raise KeyError(name)
    return server


_TRANSPORT_ERRORS = {
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "RemoteProtocolError",
    "ReadError",
    "TimeoutException",
}


def _is_transport_error(exc: BaseException) -> bool:
    """True for network-level failures (retryable), including ones wrapped in ExceptionGroups/causes."""
    if isinstance(exc, (TimeoutError, ConnectionError)) or type(exc).__name__ in _TRANSPORT_ERRORS:
        return True
    if isinstance(exc, BaseExceptionGroup):
        return all(_is_transport_error(e) for e in exc.exceptions)
    return exc.__cause__ is not None and _is_transport_error(exc.__cause__)


class ToolGateway:
    def __init__(self, budget: Budget | None = None) -> None:
        self.budget = budget or Budget()
        self.breakers: dict[str, CircuitBreaker] = {}

    async def call(
        self,
        server: str,
        tool: str,
        args: dict[str, Any],
        *,
        schema: type[BaseModel] | None = None,
        write: bool = False,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        self.budget.tool(f"{server}.{tool}", args, write=write)
        with span("tool.call", server=server, tool=tool, write=write, tenant=tenant):
            try:
                async with Client(_server_target(server)) as c:
                    result = await c.call_tool(tool, args)
            except Exception as exc:  # transport failures surface as (nested) ExceptionGroups from anyio
                if _is_transport_error(exc):
                    raise TransientError(f"{server}.{tool}: unreachable ({type(exc).__name__})") from exc
                raise
            if result.is_error:
                text = " ".join(getattr(x, "text", "") for x in result.content)
                if "TRANSIENT" in text or "timeout" in text.lower():
                    raise TransientError(f"{server}.{tool}: {text}")
                raise ToolError(f"{server}.{tool}: {text}")
            payload = result.structured_content or json.loads(result.content[0].text)
            if isinstance(payload, dict) and payload.get("error"):
                raise ToolError(f"{server}.{tool}: {payload['error']}")
            return schema.model_validate(payload).model_dump() if schema else payload
