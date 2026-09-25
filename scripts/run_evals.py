"""Run the golden-set evals.  `python scripts/run_evals.py [--azure] [--out evals-out]`

Offline (default): deterministic custom evaluators + release gate (exit 1 on regression).
--azure: also score with azure-ai-evaluation Groundedness/Relevance and log to the Foundry project
(needs FOUNDRY_PROJECT_ENDPOINT, AZURE_OPENAI_ENDPOINT, EVAL_MODEL_DEPLOYMENT, and `pip install -e .[eval]`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from agentplatform.evals.runner import hr_rows, mortgage_rows, score_azure, score_offline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--azure", action="store_true")
    ap.add_argument("--out", default="evals-out")
    a = ap.parse_args(argv)
    logging.getLogger("agent_framework").setLevel(logging.ERROR)

    async def gen():
        return await mortgage_rows(), await hr_rows()

    mortgage, hr = asyncio.run(gen())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("mortgage", mortgage), ("hr", hr)):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))
    report = score_offline(mortgage, hr)
    print(json.dumps({"metrics": report.metrics, "failures": report.failures}, indent=2))
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
