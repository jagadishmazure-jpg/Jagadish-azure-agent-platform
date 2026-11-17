"""Decide whether a canary prompt/model version should lose its traffic.

The decision is pure: stable metrics, canary metrics, the current APIM weight, and the same
release floors the offline gate uses. Higher-is-better metrics roll back when the canary drops
more than ``max_drop`` below stable or falls through its floor. ``condition_leak`` rolls back
when it rises. A missing required metric fails closed (weight goes to 0). Nothing here calls Azure.
"""

from __future__ import annotations

from typing import Any

from agentplatform.evals.runner import MAX_METRICS, THRESHOLDS

REQUIRED = ("policy_compliance", "condition_recall", "condition_leak", "recommendation_match")


def decide_rollback(
    stable: dict[str, float],
    canary: dict[str, float],
    *,
    weight: int = 10,
    max_drop: float = 0.05,
    required: tuple[str, ...] = REQUIRED,
    thresholds: dict[str, float] | None = None,
    max_metrics: set[str] | None = None,
) -> dict[str, Any]:
    if not 0 <= weight <= 100:
        raise ValueError("weight must be between 0 and 100")
    floors = THRESHOLDS if thresholds is None else thresholds
    ceilings = MAX_METRICS if max_metrics is None else max_metrics
    reasons: list[str] = []
    for metric in required:
        if metric not in stable or metric not in canary:
            reasons.append(f"{metric}: missing from stable or canary (fail closed)")
            continue
        base = float(stable[metric])
        trial = float(canary[metric])
        if metric in ceilings:
            ceiling = floors.get(metric)
            if ceiling is not None and trial > ceiling:
                reasons.append(f"{metric}: canary {trial:.3f} above ceiling {ceiling}")
            elif trial > base:
                reasons.append(f"{metric}: canary {trial:.3f} rose above stable {base:.3f}")
            continue
        floor = floors.get(metric)
        if floor is not None and trial < floor:
            reasons.append(f"{metric}: canary {trial:.3f} below release floor {floor}")
        if trial < base - max_drop:
            reasons.append(
                f"{metric}: canary {trial:.3f} dropped more than {max_drop} from stable {base:.3f}"
            )
    rollback = bool(reasons)
    return {
        "rollback": rollback,
        "previous_weight": weight,
        "new_weight": 0 if rollback else weight,
        "reasons": reasons,
        "action": "set named value canary-weight to 0" if rollback else "keep named value canary-weight",
    }


def az_rest_command(
    decision: dict[str, Any], *, subscription_id: str, resource_group: str, apim_name: str
) -> list[str]:
    """The ``az rest`` call that writes the new weight. Printed by the dry run; not executed here."""
    url = (
        "https://management.azure.com/subscriptions/"
        f"{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.ApiManagement/service/{apim_name}"
        "/namedValues/canary-weight?api-version=2024-05-01"
    )
    body = json_body(decision["new_weight"])
    return ["az", "rest", "--method", "put", "--url", url, "--body", body]


def json_body(weight: int) -> str:
    import json

    return json.dumps({"properties": {"displayName": "canary-weight", "value": str(weight)}})
