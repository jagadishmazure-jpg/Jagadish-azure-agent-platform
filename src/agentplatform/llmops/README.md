# `llmops/`: prompt runs and the canary decision

Tracks which prompt version and model produced a score, and decides whether API Management
should send the canary's traffic back to the stable version. The decision function does not
call Azure. The script prints the `az rest` update and, with `--apply`, sends it only when the
subscription, resource group and APIM name are set.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Exports `log_prompt_run` and `decide_rollback`. |
| [`tracking.py`](tracking.py) | Writes an MLflow run when `MLFLOW_TRACKING_URI` is set and `mlflow` imports. Otherwise appends the same fields to a JSONL file. |
| [`canary.py`](canary.py) | Compares stable and canary metrics to the release floors. A regression, or a missing required metric, sets the next weight to 0. |

Install the tracker backend with `pip install -e ".[llmops]"`. Without that extra, runs still record locally.

```bash
python scripts/canary_rollback.py --example regress
python scripts/canary_rollback.py --example hold
```
