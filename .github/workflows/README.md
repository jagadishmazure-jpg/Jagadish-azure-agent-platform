# `.github/workflows/`: CI, infrastructure checks, and the gated deploy pipeline

GitHub Actions for this repo. `ci.yml` runs the offline quality bar. `infra.yml` checks the
Terraform stack and container images on every pull request. `deploy.yml` and `teardown.yml` are
the deployment pipeline; their jobs are skipped unless the repository variable `DEPLOY_ENABLED`
is `true`, which it is not. Full walkthrough: [`docs/deployment.md`](../../docs/deployment.md).
(GitHub renders this README when you browse the folder; Actions only reads the `.yml` files.)

| File | What it does |
|---|---|
| [`ci.yml`](ci.yml) | Three jobs. `test` (Python 3.12): `pip install -e ".[dev]"`, `ruff check` + `ruff format --check`, `pytest -q`, `python scripts/export_agent_cards.py --check` (checked-in cards are current), `python scripts/render_docs.py --check` (failure table is current), `python scripts/doc_drift.py --check` (pasted output and code excerpts in the docs match the code), `python scripts/run_evals.py --out evals-out` (eval release gate) and uploads the eval rows as an artifact. `bicep`: installs the Bicep CLI and runs `bicep build infra/main.bicep`. A `secrets` job runs gitleaks over the full git history. |
| [`codeql.yml`](codeql.yml) | CodeQL for Python and for the workflow files (`actions`), on push, pull request and weekly. Results appear under Security -> Code scanning and do not fail the build. |
| [`infra.yml`](infra.yml) | Pull requests and `main`: `terraform fmt -check`, `init -backend=false`, `validate`, `terraform test` (mocked providers) for `infra/terraform`; tflint; checkov with [`.checkov.yaml`](../../.checkov.yaml); builds the three service images and smoke-runs the BFF. `terraform plan` runs only when the Azure OIDC variables exist, otherwise it passes with a notice. |
| [`deploy.yml`](deploy.yml) | Push to `main` or manual (`deploy_tool`: `terraform` / `bicep`). `preflight` reports the gate; `build` -> `deploy-dev` (environment `dev`) -> `deploy-prod` (environment `prod`, required reviewers). OIDC login via `azure/login`, image promotion with `az acr import`, smoke tests. All but `preflight` gated by `DEPLOY_ENABLED == 'true'`. |
| [`teardown.yml`](teardown.yml) | Manual only: destroys one environment with the tool that created it, after typing the environment name again. Same gate; runs in the environment, so prod needs approval. |

## Reproduce CI locally

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
python scripts/export_agent_cards.py --check
python scripts/run_evals.py --out evals-out
az bicep build --file infra/main.bicep --stdout > /dev/null   # or: bicep build infra/main.bicep
cd infra/terraform && terraform init -backend=false && terraform validate && terraform test
```

> **Status:** nothing in this repo has been deployed to Azure yet. The deploy pipeline is gated off; see [`docs/deployment.md`](../../docs/deployment.md).

**Supply chain.** Every third-party action is pinned to a full commit SHA with the version in a comment, and every workflow starts from `permissions: contents: read`; jobs that need more (OIDC sign-in, CodeQL uploads) ask for it themselves. Dependabot ([`../dependabot.yml`](../dependabot.yml)) proposes weekly grouped updates that move the SHA and the comment together, and `tests/test_repo_docs.py::test_workflows_are_hardened` fails CI if an action is left unpinned.

**SBOM.** The `sbom` job in `ci.yml` writes an SPDX JSON bill of materials for the source tree on every run (artifact `sbom.spdx.json`). The image job in `infra.yml` adds a Trivy scan that fails on fixable HIGH/CRITICAL findings, an SPDX image SBOM and, on `main`, keyless build provenance for the image archive (`actions/attest-build-provenance`); see [`SECURITY.md`](../../SECURITY.md) for how to verify it.
