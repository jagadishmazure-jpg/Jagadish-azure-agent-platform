# `services/mcp/`: container image for one MCP server per container (streamable HTTP at `/mcp`)

Dockerfile for one MCP server per container (streamable HTTP at `/mcp`). Select the server with the `MCP_SERVER` env var or the first argument (`credit-bureau`, `los`). azd services `mcp-credit-bureau` and `mcp-los`. The image is a two-stage build from the repo root: the first
stage builds a wheel of `agentplatform`, the second installs it into `python:3.12-slim`, runs as
a non-root user and listens on port 8080 (`PORT`).

| File | What it does |
|---|---|
| [`Dockerfile`](Dockerfile) | Multi-stage build; final command `python -m agentplatform.mcp_servers`. Build with `docker build -f services/mcp/Dockerfile -t aap-mcp .` from the repo root. |

Used by [`docker-compose.yml`](../../docker-compose.yml) for a local containerised run and by
[`azure.yaml`](../../azure.yaml) for `azd deploy` (remote build in ACR). The Dockerfiles have not
been built on the authoring machine (no Docker there); `make mesh` runs the same topology as
plain processes.
