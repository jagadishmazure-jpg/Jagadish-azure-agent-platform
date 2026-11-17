"""Run the golden-set evals.  `python scripts/run_evals.py [--azure] [--live] [--out evals-out]`

Offline (default): deterministic custom evaluators + release gate (exit 1 on regression).
--azure: also score with azure-ai-evaluation Groundedness/Relevance and log to the Foundry project
(needs FOUNDRY_PROJECT_ENDPOINT, AZURE_OPENAI_ENDPOINT, EVAL_MODEL_DEPLOYMENT, and `pip install -e .[eval]`).
--live: same judges via the live-eval report (mock vs live, human agreement, USD per 1k tasks,
optional LangSmith). Exits 0 and writes the report when those env vars are absent. The offline
gate still applies.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from agentplatform.evals.live import run_live_evaluation
from agentplatform.evals.runner import hr_rows, mortgage_rows, score_azure, score_offline


def _write_json(path: Path, payload: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--azure", action="store_true")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Score with Azure AI Evaluation SDK. Skips cleanly when AZURE_OPENAI_ENDPOINT is unset.",
    )
    ap.add_argument(
        "--prompt-ref", default="", help="Pin a prompt ref such as mortgage.critic@1.1.0 for this run."
    )
    ap.add_argument("--out", default="evals-out")
    a = ap.parse_args(argv)
    logging.getLogger("agent_framework").setLevel(logging.ERROR)

    async def gen():
        return await mortgage_rows(), await hr_rows()

    from agentplatform.llmops.selection import REQUEST_PROMPT_REF

    prompt_token = REQUEST_PROMPT_REF.set(a.prompt_ref)
    try:
        mortgage, hr = asyncio.run(gen())
    finally:
        REQUEST_PROMPT_REF.reset(prompt_token)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("mortgage", mortgage), ("hr", hr)):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))
    report = score_offline(mortgage, hr)
    print(json.dumps({"metrics": report.metrics, "failures": report.failures}, indent=2))
    if a.live:
        report_path = out / "live-report.json"
        report_path.unlink(missing_ok=True)
        try:
            live = run_live_evaluation(mortgage, hr, env=os.environ)
        except Exception as exc:
            _write_json(report_path, {"ok": False, "error": f"{exc.__class__.__name__}: {exc}", "live": None})
            raise
        live["prompt_ref"] = a.prompt_ref or "pack-default"
        print(json.dumps(live, indent=2))
        _write_json(report_path, live)
    if a.azure:
        for name in ("mortgage", "hr"):
            res = score_azure(
                out / f"{name}.jsonl",
                os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                os.environ["AZURE_OPENAI_ENDPOINT"],
                os.environ.get("EVAL_MODEL_DEPLOYMENT", "gpt-5-mini"),
            )
            print(name, json.dumps(res, indent=2, default=str))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
