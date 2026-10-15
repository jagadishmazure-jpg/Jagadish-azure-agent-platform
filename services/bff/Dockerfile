# Experience-plane BFF / orchestrator (FastAPI + MAF mortgage graph + single agents)
# Build from the repo root:  docker build -f services/bff/Dockerfile -t aap-bff .
# Base image pinned by digest (tag kept for readability); Dependabot's docker ecosystem bumps both.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
ENV PYTHONUNBUFFERED=1 PORT=8080 AAP_CHECKPOINT_DIR=/tmp/checkpoints
RUN useradd --create-home --uid 10001 app
COPY --from=build /wheels /wheels
# pip is only needed to install the wheels; it is not shipped in the runtime image.
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels && python -m pip uninstall -y pip
USER app
EXPOSE 8080
CMD ["uvicorn", "agentplatform.bff:app", "--host", "0.0.0.0", "--port", "8080"]
