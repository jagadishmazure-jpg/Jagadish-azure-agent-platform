# `services/bff/`: container image for the experience-plane BFF / orchestrator

Dockerfile for the experience-plane BFF / orchestrator. Runs the FastAPI BFF (`agentplatform.bff:app`) with the in-process MAF mortgage graph and single agents. azd service `bff`; the only externally reachable app, behind APIM. The image is a two-stage build from the repo root: the first
stage builds a wheel of `agentplatform`, the second installs it into `python:3.12-slim`, runs as
a non-root user and listens on port 8080 (`PORT`).

| File | What it does |
|---|---|
| [`Dockerfile`](Dockerfile) | Multi-stage build; final command `uvicorn agentplatform.bff:app --host 0.0.0.0 --port 8080`. Build with `docker build -f services/bff/Dockerfile -t aap-bff .` from the repo root. |

Used by [`docker-compose.yml`](../../docker-compose.yml) for a local containerised run and by
[`azure.yaml`](../../azure.yaml) for `azd deploy` (remote build in ACR). The Dockerfiles have not
been built on the authoring machine (no Docker there); `make mesh` runs the same topology as
plain processes.
