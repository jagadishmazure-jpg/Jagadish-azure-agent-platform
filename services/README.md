# `services/`: container images

One Dockerfile per runtime plane. Each image installs the package, runs as a non-root user (uid 10001) and is deployed as its own Azure Container App.

| Folder | Image |
|---|---|
| [`bff/`](bff/README.md) | FastAPI experience plane (`agentplatform.bff:app`) |
| [`a2a/`](a2a/README.md) | One A2A agent per container (`AGENT_ID`) |
| [`mcp/`](mcp/README.md) | One MCP server per container (`MCP_SERVER`) |

Build locally with `docker compose up --build`, or run every service as a process with `make mesh`. See [docs/components/bff-and-services.md](../docs/components/bff-and-services.md).
