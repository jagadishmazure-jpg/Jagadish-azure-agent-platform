# `.github/workflows/`: CI and (disabled) deploy

GitHub Actions for this repo. `ci.yml` runs the full offline quality bar on every push to
`main` and every pull request. `deploy.yml` is a manual `azd` deployment over GitHub OIDC that
stays disabled unless the repository variable `ENABLE_DEPLOY` is `true`; it has not been run.
(GitHub renders this README when you browse the folder; Actions only reads the `.yml` files.)

| File | What it does |
|---|---|
| [`ci.yml`](ci.yml) | Two jobs. `test` (Python 3.12): `pip install -e ".[dev]"`, `ruff check` + `ruff format --check`, `pytest -q`, `python scripts/export_agent_cards.py --check` (checked-in cards are current), `python scripts/run_evals.py --out evals-out` (eval release gate) and uploads the eval rows as an artifact. `bicep`: installs the Bicep CLI and runs `bicep build infra/main.bicep`. |
| [`deploy.yml`](deploy.yml) | Manual (`workflow_dispatch`) `azd` provision + deploy using workload identity federation (no stored secrets). Guarded by `ENABLE_DEPLOY == 'true'`; one-time setup is described in [`docs/deploy.md`](../../docs/deploy.md). |

## Reproduce CI locally

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
python scripts/export_agent_cards.py --check
python scripts/run_evals.py --out evals-out
az bicep build --file infra/main.bicep --stdout > /dev/null   # or: bicep build infra/main.bicep
```

> **Status:** nothing in this repo has been deployed to Azure yet. The Azure code paths follow verified SDK signatures but have only run offline; see the root README's *Honest limitations*.
