# `llmops/`: prompt runs and the canary decision

Tracks which prompt version and model produced a score, and decides whether API Management
should send the canary's traffic back to the stable version. The decision function does not
call Azure. The script prints the `az rest` update. `--apply` checks the subscription, resource group and APIM name, then prints that command for an operator to run. It does not execute it.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package marker. Callers import `tracking`, `canary` or `selection` directly so the mortgage agents can read the canary headers without loading the eval runner. |
| [`tracking.py`](tracking.py) | Writes an MLflow run when `MLFLOW_TRACKING_URI` is set and `mlflow` imports. Otherwise appends the same fields to a JSONL file. |
| [`canary.py`](canary.py) | Compares stable and canary metrics to the release floors. A regression, or a missing required metric, sets the next weight to 0. |

Install the tracker backend with `pip install -e ".[llmops]"`. Without that extra, runs still record locally.

```bash
python scripts/canary_rollback.py --example regress
python scripts/canary_rollback.py --example hold
```
