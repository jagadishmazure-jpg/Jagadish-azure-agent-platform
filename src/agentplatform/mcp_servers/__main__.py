"""Serve an MCP server over streamable HTTP: `python -m agentplatform.mcp_servers credit-bureau`."""

from __future__ import annotations

import os
import sys

import uvicorn


def main() -> None:
    name = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MCP_SERVER", "credit-bureau")).strip()
    if name == "credit-bureau":
        from agentplatform.mcp_servers.credit_bureau import server
    elif name == "los":
        from agentplatform.mcp_servers.los import server
    else:
        raise SystemExit(f"unknown MCP server {name}")
    from agentplatform.harness.tracing import configure_tracing

    configure_tracing(f"mcp-{name}")
    app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, host="0.0.0.0")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
