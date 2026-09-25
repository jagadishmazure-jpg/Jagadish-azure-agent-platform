# Experience-plane BFF / orchestrator (FastAPI + MAF mortgage graph + single agents)
# Build from the repo root:  docker build -f services/bff/Dockerfile -t aap-bff .
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
CMD ["uvicorn", "agentplatform.bff:app", "--host", "0.0.0.0", "--port", "8080"]
