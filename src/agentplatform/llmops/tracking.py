"""Record a prompt/model run the way MLflow does.

When ``MLFLOW_TRACKING_URI`` is set and the ``mlflow`` package imports, the run goes to that
tracking server or file store. Otherwise the same fields are appended to a local JSONL file.
Tests and laptops without MLflow use the file backend; a live project points the URI at a
workspace and installs the ``llmops`` extra.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def log_prompt_run(
    *,
    experiment: str,
    prompt_ref: str,
    prompt_sha: str,
    model: str,
    metrics: dict[str, float],
    params: dict[str, Any] | None = None,
    tracking_uri: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    record_params = {"prompt_ref": prompt_ref, "prompt_sha": prompt_sha, "model": model, **(params or {})}
    uri = tracking_uri if tracking_uri is not None else os.environ.get("MLFLOW_TRACKING_URI", "")
    if uri:
        try:
            import mlflow
        except ImportError:
            written = _file_log(experiment, record_params, metrics, path)
            written["note"] = "MLFLOW_TRACKING_URI is set but mlflow is not installed; wrote a file record"
            return written
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(experiment)
        with mlflow.start_run() as run:
            mlflow.log_params({key: str(value) for key, value in record_params.items()})
            mlflow.log_metrics({key: float(value) for key, value in metrics.items()})
            run_id = run.info.run_id
        return {
            "backend": "mlflow",
            "experiment": experiment,
            "run_id": run_id,
            "params": record_params,
            "metrics": metrics,
        }
    return _file_log(experiment, record_params, metrics, path)


def _file_log(
    experiment: str, params: dict[str, Any], metrics: dict[str, float], path: Path | None
) -> dict[str, Any]:
    dest = path or Path("llmops-out") / "experiments.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    record = {"backend": "file", "experiment": experiment, "params": params, "metrics": metrics}
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    record["path"] = str(dest)
    return record
