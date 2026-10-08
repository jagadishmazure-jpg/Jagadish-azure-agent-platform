# Experience-plane BFF / orchestrator (FastAPI + MAF mortgage graph + single agents)
# Build from the repo root:  docker build -f services/bff/Dockerfile -t aap-bff .
# Base image pinned by digest (tag kept for readability); Dependabot's docker ecosystem bumps both.
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
ENV PYTHONUNBUFFERED=1 PORT=8080 AAP_CHECKPOINT_DIR=/tmp/checkpoints
RUN useradd --create-home --uid 10001 app
COPY --from=build /wheels /wheels
# pip is only needed to install the wheels; it is not shipped in the runtime image.
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels && python -m pip uninstall -y pip
USER app
EXPOSE 8080
CMD ["uvicorn", "agentplatform.bff:app", "--host", "0.0.0.0", "--port", "8080"]
