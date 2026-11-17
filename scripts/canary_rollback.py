"""Simulate the APIM canary rollback decision. Never calls Azure.

Reads two eval metric JSON objects (the ``metrics`` map from ``run_evals.py``), decides whether
the canary prompt/model regressed, and prints the ``az rest`` call that would set the
``canary-weight`` named value. ``--example regress`` and ``--example hold`` need no files.

``--apply`` checks ``AZURE_SUBSCRIPTION_ID``, ``AZURE_RESOURCE_GROUP`` and ``APIM_NAME`` and
prints the command for an operator to run. It does not execute that command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    # Live reports nest the release-gate scores under mock.metrics. A top-level metrics map
    # is the offline gate report. Live judge names are a different instrument and are not the gate.
    nested = payload.get("mock")
    if isinstance(nested, dict) and isinstance(nested.get("metrics"), dict):
        metrics = nested["metrics"]
    else:
        metrics = payload.get("metrics", payload)
    if not isinstance(metrics, dict):
        return {}
    return {key: float(value) for key, value in metrics.items() if isinstance(value, (int, float))}


_SUBSCRIPTION = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_RESOURCE_GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
_APIM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,49}$")


def _apply_problem(subscription: str, resource_group: str, apim_name: str) -> str:
    if not (subscription and resource_group and apim_name):
        return "refusing --apply without AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP and APIM_NAME"
    if not (
        _SUBSCRIPTION.match(subscription)
        and _RESOURCE_GROUP.match(resource_group)
        and _APIM_NAME.match(apim_name)
    ):
        return (
            "refusing --apply: subscription, resource group or APIM name does not match the expected pattern"
        )
    return ""


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
        "--apply",
        action="store_true",
        help="Require the Azure resource names and print the az rest command. Does not execute it.",
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
    # A hold must not hand the operator a PUT that would rewrite the weight to the CLI default.
    command = (
        az_rest_command(
            decision,
            subscription_id=subscription or "<subscription>",
            resource_group=resource_group or "<resource-group>",
            apim_name=apim_name or "<apim>",
        )
        if decision["rollback"]
        else None
    )
    applied = False
    if args.apply:
        problem = _apply_problem(subscription, resource_group, apim_name)
        if problem:
            print(json.dumps({"applied": False, "error": problem, "decision": decision}, indent=2))
            return 2
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
