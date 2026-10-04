# `.github/`: automation and ownership

| Path | What it holds |
|---|---|
| [`workflows/`](workflows/README.md) | `ci.yml` (lint, tests, agent-card and doc-drift checks, evals, Bicep build), `infra.yml`, gated `deploy.yml` and `teardown.yml` |
| [`scripts/`](scripts/README.md) | Shell steps used by the deploy workflows |
| `CODEOWNERS` | `* @jagadishmazure-jpg`: every change needs the owner's review |
