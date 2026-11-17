"""Live eval mode: Azure AI Evaluation SDK judges on Azure OpenAI, optional LangSmith.

Offline golden-set scoring stays the default. This module adds a second pass that calls
Foundry-hosted Azure OpenAI through ``azure-ai-evaluation`` when the endpoint and deployment
are set. With those variables absent it returns a report and does not raise, so CI and laptops
without a subscription stay green.

The deterministic release gate and the LLM judges are different instruments. The report places
them side by side and does not subtract one from the other.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from agentplatform.evals.pricing import INPUT_USD_PER_1M, OUTPUT_USD_PER_1M, cost_per_1k_tasks
from agentplatform.evals.runner import score_offline

LABELS = Path(__file__).parent / "golden" / "human_labels.jsonl"
JUDGE_COUNT = 2
_CITE = re.compile(r"\[([A-Za-z0-9._-]+)\]")
_STOP = frozenset(
    [
        "what",
        "how",
        "many",
        "the",
        "are",
        "can",
        "per",
        "and",
        "for",
        "you",
        "your",
        "does",
        "this",
        "that",
        "with",
        "from",
    ]
)


def deployment_name(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    return (
        env.get("EVAL_MODEL_DEPLOYMENT")
        or env.get("AZURE_OPENAI_DEPLOYMENT")
        or env.get("FOUNDRY_MODEL")
        or ""
    ).strip()


def missing_live_env(env: dict[str, str] | None = None) -> list[str]:
    """Variables a live judge call needs. Empty means the SDK path can run."""
    env = env if env is not None else os.environ
    missing = []
    if not env.get("AZURE_OPENAI_ENDPOINT", "").strip():
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not deployment_name(env):
        missing.append("EVAL_MODEL_DEPLOYMENT")
    return missing


def load_human_labels(path: Path | None = None) -> list[dict[str, Any]]:
    src = path or LABELS
    return [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]


def lexical_judge(row: dict[str, Any]) -> dict[str, float]:
    """Offline stand-in for the LLM judge, used for the human-agreement baseline.

    Grounded when every bracketed citation appears in the context and the answer is not a
    denial the context does not support. Relevant when a content word from the query appears
    in the answer. A wrong number with a valid citation still scores grounded: that miss is
    why the labeled sample disagrees with this judge on purpose.
    """
    response = str(row.get("response") or "")
    context = str(row.get("context") or "")
    query = str(row.get("query") or "").lower()
    cites = _CITE.findall(response)
    cited_ok = bool(cites) and all(cite in context for cite in cites)
    denial = bool(re.search(r"\b(denied|denial)\b", response, re.I)) and "denied" not in context.lower()
    grounded = 1.0 if cited_ok and not denial else 0.0
    words = {w for w in re.findall(r"[a-z0-9]+", query) if len(w) > 3 and w not in _STOP}
    relevant = 1.0 if any(word in response.lower() for word in words) else 0.0
    return {"groundedness": grounded, "relevance": relevant}


def cohens_kappa(human: list[int], judge: list[int]) -> float | None:
    n = len(human)
    if n == 0 or n != len(judge):
        return None
    if n == 1:
        return 1.0 if human[0] == judge[0] else 0.0
    agree = sum(a == b for a, b in zip(human, judge, strict=True)) / n

    def rate(label: int, seq: list[int]) -> float:
        return sum(item == label for item in seq) / n

    expected = sum(rate(label, human) * rate(label, judge) for label in (0, 1))
    if expected == 1:
        return 1.0
    return (agree - expected) / (1 - expected)


def agreement(
    rows: list[dict[str, Any]], *, judge_key: str, human_key: str, threshold: float = 0.5
) -> dict[str, Any]:
    human: list[int] = []
    judge: list[int] = []
    disagreements: list[str] = []
    for row in rows:
        if judge_key not in row or human_key not in row:
            continue
        human_bit = int(row[human_key])
        judge_bit = 1 if float(row[judge_key]) >= threshold else 0
        human.append(human_bit)
        judge.append(judge_bit)
        if human_bit != judge_bit and row.get("id") is not None:
            disagreements.append(str(row["id"]))
    n = len(human)
    matches = sum(a == b for a, b in zip(human, judge, strict=True))
    return {
        "metric": judge_key,
        "n": n,
        "accuracy": (matches / n) if n else None,
        "cohens_kappa": cohens_kappa(human, judge),
        "disagreements": disagreements,
    }


def estimate_tokens(rows: list[dict[str, Any]]) -> tuple[int, int]:
    chars = 0
    for row in rows:
        chars += len(str(row.get("query") or ""))
        chars += len(str(row.get("response") or ""))
        chars += len(str(row.get("context") or ""))
    prompt = max(1, chars // 4) * JUDGE_COUNT
    completion = 180 * max(1, len(rows)) * JUDGE_COUNT
    return prompt, completion


def cost_report(
    rows: list[dict[str, Any]], *, prompt_tokens: int | None = None, completion_tokens: int | None = None
) -> dict[str, Any]:
    measured = prompt_tokens is not None and completion_tokens is not None
    if not measured:
        prompt_tokens, completion_tokens = estimate_tokens(rows)
    tasks = len(rows)
    per_1k = cost_per_1k_tasks(prompt_tokens, completion_tokens, tasks)
    batch = (prompt_tokens / 1_000_000) * INPUT_USD_PER_1M + (
        completion_tokens / 1_000_000
    ) * OUTPUT_USD_PER_1M
    return {
        "tasks": tasks,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "usd_for_batch": round(batch, 6),
        "usd_per_1k_tasks": round(per_1k, 6),
        "rates_usd_per_1m_tokens": {
            "input": INPUT_USD_PER_1M,
            "output": OUTPUT_USD_PER_1M,
            "illustrative": True,
        },
        "measured": measured,
    }


def judge_vs_human(labels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Agreement between the lexical judge and the checked-in human labels."""
    rows = []
    for label in labels if labels is not None else load_human_labels():
        scored = dict(label)
        scored.update(lexical_judge(label))
        rows.append(scored)
    grounded = agreement(rows, judge_key="groundedness", human_key="human_grounded")
    relevant = agreement(rows, judge_key="relevance", human_key="human_relevant")
    return {"judge": "lexical", "groundedness": grounded, "relevance": relevant}


_CANONICAL_METRICS = ("groundedness", "relevance", "coherence", "fluency")


def _normalize_metrics(raw: dict[str, Any]) -> dict[str, float]:
    """Collapse ``groundedness.gpt_groundedness`` to ``groundedness``."""
    out: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        parts = key.split(".")
        short = parts[-1]
        for canonical in _CANONICAL_METRICS:
            if canonical in parts or canonical in short:
                short = canonical
                break
        out[short] = float(value)
    return out


def evaluate_with_sdk(rows: list[dict[str, Any]], env: dict[str, str]) -> dict[str, Any]:
    """Call azure-ai-evaluation against Azure OpenAI. Optional Foundry project logging."""
    from azure.ai.evaluation import GroundednessEvaluator, RelevanceEvaluator, evaluate

    from agentplatform.config import azure_credential

    missing = missing_live_env(env)
    if missing:
        raise RuntimeError(f"live eval env is incomplete: {', '.join(missing)}")
    model_config = {
        "azure_endpoint": env["AZURE_OPENAI_ENDPOINT"].strip(),
        "azure_deployment": deployment_name(env),
        "api_version": env.get("AZURE_OPENAI_API_VERSION", "2024-10-21").strip() or "2024-10-21",
    }
    cred = azure_credential()
    payload = [{k: row.get(k) for k in ("id", "query", "response", "context")} for row in rows]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "live.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in payload), encoding="utf-8")
        kwargs: dict[str, Any] = {
            "data": str(path),
            "evaluation_name": "aap-live-golden",
            "evaluators": {
                "groundedness": GroundednessEvaluator(model_config, credential=cred),
                "relevance": RelevanceEvaluator(model_config, credential=cred),
            },
            "evaluator_config": {
                "groundedness": {
                    "column_mapping": {
                        "query": "${data.query}",
                        "response": "${data.response}",
                        "context": "${data.context}",
                    }
                },
                "relevance": {"column_mapping": {"query": "${data.query}", "response": "${data.response}"}},
            },
            "tags": {"repo": "azure-agent-platform", "mode": "live"},
        }
        project = env.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
        if project:
            kwargs["azure_ai_project"] = project
        result = evaluate(**kwargs)
    metrics = _normalize_metrics(result.get("metrics") or {})
    per_row = result.get("rows") or []
    return {
        "metrics": metrics,
        "rows": per_row,
        "studio_url": result.get("studio_url"),
        "foundry_project": bool(project),
    }


def log_langsmith(summary: dict[str, Any], env: dict[str, str], client: Any = None) -> dict[str, Any]:
    """Optional experiment log. Absent key or package is a skip, not a failure."""
    if not env.get("LANGSMITH_API_KEY", "").strip():
        return {"logged": False, "reason": "LANGSMITH_API_KEY not set"}
    if client is None:
        try:
            from langsmith import Client
        except ImportError:
            return {"logged": False, "reason": "langsmith is not installed"}
        client = Client(api_key=env["LANGSMITH_API_KEY"].strip())
    project = (env.get("LANGSMITH_PROJECT") or env.get("LANGCHAIN_PROJECT") or "azure-agent-platform").strip()
    try:
        client.create_run(
            name="aap-live-eval",
            run_type="chain",
            inputs={"tasks": summary.get("cost", {}).get("tasks", 0)},
            outputs={"live": summary.get("live"), "agreement": summary.get("judge_vs_human")},
            project_name=project,
        )
    except Exception as exc:
        return {"logged": False, "reason": f"langsmith call failed: {exc.__class__.__name__}"}
    return {"logged": True, "project": project}


def run_live_evaluation(
    mortgage: list[dict[str, Any]],
    hr: list[dict[str, Any]],
    *,
    env: dict[str, str] | None = None,
    evaluate_fn: Any = None,
    langsmith_client: Any = None,
    labels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score the golden rows. Calls Azure only when ``evaluate_fn`` is passed or env is complete."""
    env = dict(os.environ if env is None else env)
    mock = score_offline(mortgage, hr)
    labels = labels if labels is not None else load_human_labels()
    judged_rows = list(mortgage) + list(hr) + list(labels)
    missing = missing_live_env(env)
    report: dict[str, Any] = {
        "mode": "live",
        "skipped": bool(missing),
        "reason": "" if not missing else f"skipped: set {', '.join(missing)}",
        "target_mode": env.get("AAP_MODE", "offline") or "offline",
        "mock": {"metrics": mock.metrics, "failures": mock.failures, "passed": mock.passed},
        "live": None,
        "comparison": {
            "note": (
                "mock.metrics are the deterministic release gate on the golden workflow. "
                "live.metrics are Azure AI Evaluation SDK judges (Groundedness, Relevance) "
                "on the same rows plus the human-labeled sample. Do not subtract them."
            )
        },
        "judge_vs_human": judge_vs_human(labels),
        "cost": cost_report(judged_rows),
        "langsmith": {"logged": False, "reason": "live eval skipped"} if missing else {},
        "foundry_project": bool(env.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()),
    }
    if missing and evaluate_fn is None:
        report["cost"]["live_calls"] = 0
        return report

    fn = evaluate_fn or evaluate_with_sdk
    live = fn(judged_rows, env)
    report["skipped"] = False
    report["reason"] = ""
    report["live"] = {
        "metrics": _normalize_metrics(live.get("metrics") or {}),
        "studio_url": live.get("studio_url"),
        "foundry_logged": bool(live.get("foundry_project")),
    }
    per_row = {str(row.get("id")): row for row in live.get("rows") or [] if row.get("id") is not None}
    if per_row:
        joined = []
        for label in labels:
            judge_row = per_row.get(str(label["id"]))
            if not judge_row:
                continue
            joined.append({**label, **_normalize_metrics(judge_row)})
        if joined:
            report["judge_vs_human_live"] = {
                "judge": "azure-ai-evaluation",
                "groundedness": agreement(joined, judge_key="groundedness", human_key="human_grounded"),
                "relevance": agreement(joined, judge_key="relevance", human_key="human_relevant"),
            }
    else:
        report["judge_vs_human_live"] = {
            "judge": "azure-ai-evaluation",
            "available": False,
            "reason": "evaluator did not return per-row scores",
        }
    usage = live.get("usage") or {}
    if usage.get("prompt_tokens") is not None:
        report["cost"] = cost_report(
            judged_rows,
            prompt_tokens=int(usage["prompt_tokens"]),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )
    report["cost"]["live_calls"] = JUDGE_COUNT
    report["langsmith"] = log_langsmith(report, env, client=langsmith_client)
    return report
