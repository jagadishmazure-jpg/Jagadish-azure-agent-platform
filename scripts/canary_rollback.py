"""Simulate the APIM canary rollback decision. Offline unless ``--apply`` is passed.

Reads two eval metric JSON objects (the ``metrics`` map from ``run_evals.py``), decides whether
the canary prompt/model regressed, and prints the ``az rest`` call that would set the
``canary-weight`` named value. ``--example regress`` and ``--example hold`` need no files.

``--apply`` calls Azure only when ``AZURE_SUBSCRIPTION_ID``, ``AZURE_RESOURCE_GROUP`` and
``APIM_NAME`` are set. The default is a dry run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from agentplatform.llmops.canary import az_rest_command, decide_rollback
from agentplatform.llmops.tracking import log_prompt_run
from agentplatform.prompts.prompty import load_prompty_pack

STABLE = {
    "policy_compliance": 1.0,
    "condition_recall": 1.0,
    "condition_leak": 0.0,
    "recommendation_match": 1.0,
}
REGRESSED = {
    "policy_compliance": 0.8,
    "condition_recall": 0.9,
    "condition_leak": 0.0,
    "recommendation_match": 1.0,
}


def _load_metrics(path: str) -> dict[str, float]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    metrics = payload.get("metrics", payload)
    return {key: float(value) for key, value in metrics.items() if isinstance(value, (int, float))}


def _metric_pair(
    parser: argparse.ArgumentParser, example: str | None, stable_path: str | None, canary_path: str | None
) -> tuple[dict[str, float], dict[str, float]]:
    """Both maps are assigned on every path. ``parser.error`` stops the process; the raise is for analyzers."""
    if example == "regress":
        return dict(STABLE), dict(REGRESSED)
    if example == "hold":
        return dict(STABLE), dict(STABLE)
    if stable_path and canary_path:
        return _load_metrics(stable_path), _load_metrics(canary_path)
    parser.error("pass --example or both --stable and --canary")
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decide an APIM canary rollback from two eval reports")
    parser.add_argument("--stable", help="JSON file with stable metrics")
    parser.add_argument("--canary", help="JSON file with canary metrics")
    parser.add_argument("--example", choices=("regress", "hold"), help="Use built-in metric pairs; no files")
    parser.add_argument("--weight", type=int, default=10)
    parser.add_argument("--max-drop", type=float, default=0.05)
    parser.add_argument(
        "--apply", action="store_true", help="Call Azure. Refuses when subscription env is missing."
    )
    parser.add_argument("--track-dir", default="", help="Where to append the file-backend experiment record")
    args = parser.parse_args(argv)

    stable, canary = _metric_pair(parser, args.example, args.stable, args.canary)
    decision = decide_rollback(stable, canary, weight=args.weight, max_drop=args.max_drop)
    pack = load_prompty_pack()
    stable_prompt = pack.get("mortgage.critic", "1.0.0")
    canary_prompt = pack.get("mortgage.critic", "1.1.0")
    track_path = Path(args.track_dir) / "experiments.jsonl" if args.track_dir else None
    tracked = log_prompt_run(
        experiment="canary-rollback",
        prompt_ref=canary_prompt.ref,
        prompt_sha=canary_prompt.sha,
        model=canary_prompt.deployment,
        metrics={key: float(canary[key]) for key in canary},
        params={
            "stable_ref": stable_prompt.ref,
            "rollback": decision["rollback"],
            "new_weight": decision["new_weight"],
        },
        path=track_path,
    )
    subscription = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    resource_group = os.environ.get("AZURE_RESOURCE_GROUP", "").strip()
    apim_name = os.environ.get("APIM_NAME", "").strip()
    command = az_rest_command(
        decision,
        subscription_id=subscription or "<subscription>",
        resource_group=resource_group or "<resource-group>",
        apim_name=apim_name or "<apim>",
    )
    applied = False
    if args.apply:
        if not (subscription and resource_group and apim_name):
            print(
                json.dumps(
                    {
                        "applied": False,
                        "error": "refusing --apply without AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP and APIM_NAME",
                        "decision": decision,
                    },
                    indent=2,
                )
            )
            return 2
        subprocess.run(command, check=True)
        applied = True
    report = {
        "decision": decision,
        "stable_prompt": stable_prompt.ref,
        "canary_prompt": canary_prompt.ref,
        "command": command,
        "applied": applied,
        "tracking": {"backend": tracked["backend"], "experiment": tracked["experiment"]},
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
