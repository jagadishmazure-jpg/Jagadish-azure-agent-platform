# `services/a2a/`: container image for one A2A agent per container

Dockerfile for one A2A agent per container. Select the agent with the `AGENT_ID` env var or the first argument (`underwriting-agent`, `crm-agent`, `erp-agent`, `*-standin`). azd deploys it as `a2a-underwriting`, `a2a-crm` and `a2a-erp`; the stand-ins are commented out in `azure.yaml`. The image is a two-stage build from the repo root: the first
stage builds a wheel of `agentplatform`, the second installs it into `python:3.12-slim`, runs as
a non-root user and listens on port 8080 (`PORT`).

| File | What it does |
|---|---|
| [`Dockerfile`](Dockerfile) | Multi-stage build; final command `python -m agentplatform.a2a`. Build with `docker build -f services/a2a/Dockerfile -t aap-a2a .` from the repo root. |

Used by [`docker-compose.yml`](../../docker-compose.yml) for a local containerised run and by
[`azure.yaml`](../../azure.yaml) for `azd deploy` (remote build in ACR). The Dockerfiles have not
been built on the authoring machine (no Docker there); `make mesh` runs the same topology as
plain processes.
