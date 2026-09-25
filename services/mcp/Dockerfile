# One MCP server per container (streamable HTTP at /mcp); select with MCP_SERVER env or first arg (credit-bureau, los)
# Build from the repo root:  docker build -f services/mcp/Dockerfile -t aap-mcp .
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=8080 AAP_CHECKPOINT_DIR=/tmp/checkpoints
RUN useradd --create-home --uid 10001 app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER app
EXPOSE 8080
CMD ["python", "-m", "agentplatform.mcp_servers"]
