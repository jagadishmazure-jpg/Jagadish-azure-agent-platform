# One MCP server per container (streamable HTTP at /mcp); select with MCP_SERVER env or first arg (credit-bureau, los)
# Build from the repo root:  docker build -f services/mcp/Dockerfile -t aap-mcp .
# Base image pinned by digest (tag kept for readability); Dependabot's docker ecosystem bumps both.
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
ENV PYTHONUNBUFFERED=1 PORT=8080 AAP_CHECKPOINT_DIR=/tmp/checkpoints
RUN useradd --create-home --uid 10001 app
COPY --from=build /wheels /wheels
# pip is only needed to install the wheels; it is not shipped in the runtime image.
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels && python -m pip uninstall -y pip
USER app
EXPOSE 8080
CMD ["python", "-m", "agentplatform.mcp_servers"]
