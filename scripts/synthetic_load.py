"""Synthetic traffic against the BFF or the APIM gateway.

Default is a dry run: print the requests and exit. Pass ``--execute`` to send them.
Loan ids and questions are the same synthetic files the offline demo uses. No customer data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

SCENARIOS: list[dict[str, Any]] = [
    {"method": "GET", "path": "/healthz", "json": None},
    {"method": "POST", "path": "/loans/L-1001/underwrite", "json": None},
    {"method": "POST", "path": "/loans/L-1002/underwrite", "json": None},
    {"method": "POST", "path": "/loans/L-1003/underwrite", "json": None},
    {"method": "GET", "path": "/directory", "json": None},
    {
        "method": "POST",
        "path": "/chat/hr",
        "json": {"message": "How many weeks of parental leave do I get?"},
    },
    {"method": "POST", "path": "/chat/it", "json": {"message": "I need a password reset for my laptop."}},
]


def build_plan(base_url: str, rounds: int = 1, api_prefix: str = "") -> list[dict[str, Any]]:
    """Build the request list.

    Loan underwrites run once. Later rounds repeat only the read and chat calls, so a
    multi-round pass does not open a second review of the same loan. ``api_prefix`` is
    ``agents`` when the base URL is the APIM gateway (the API is mounted there, and it has
    no ``/healthz``).
    """
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    prefix = "/" + api_prefix.strip("/") if api_prefix.strip("/") else ""
    root = base_url.rstrip("/")
    plan = []
    for index in range(rounds):
        for scenario in SCENARIOS:
            if prefix and scenario["path"] == "/healthz":
                continue
            if index > 0 and scenario["path"].startswith("/loans/"):
                continue
            path = prefix + scenario["path"]
            plan.append(
                {
                    "round": index,
                    "method": scenario["method"],
                    "path": path,
                    "url": root + path,
                    "json": scenario["json"],
                }
            )
    return plan


def execute(
    plan: list[dict[str, Any]], client: Any, headers: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    results = []
    for item in plan:
        started = time.perf_counter()
        response = client.request(item["method"], item["url"], json=item["json"], headers=headers)
        results.append(
            {
                "round": item["round"],
                "method": item["method"],
                "path": item["path"],
                "status": response.status_code,
                "seconds": round(time.perf_counter() - started, 4),
            }
        )
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"requests": 0}
    statuses: dict[str, int] = {}
    for row in results:
        statuses[str(row["status"])] = statuses.get(str(row["status"]), 0) + 1
    latencies = sorted(row["seconds"] for row in results)
    return {
        "requests": len(results),
        "statuses": statuses,
        "latency_seconds": {
            "min": latencies[0],
            "p50": latencies[len(latencies) // 2],
            "max": latencies[-1],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic load for the agent platform BFF")
    parser.add_argument("--base-url", default=os.environ.get("BFF_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument(
        "--api-prefix",
        default="",
        help="Path prefix. Use 'agents' when --base-url is the APIM gateway URL.",
    )
    parser.add_argument(
        "--execute", action="store_true", help="Send the requests. Without this flag, nothing is called."
    )
    parser.add_argument("--out", default="", help="Write the JSON report here as well as stdout")
    args = parser.parse_args(argv)
    plan = build_plan(args.base_url, args.rounds, args.api_prefix)
    key = os.environ.get("APIM_SUBSCRIPTION_KEY", "").strip()
    headers = {"Ocp-Apim-Subscription-Key": key} if key else {}
    if not args.execute:
        report = {
            "dry_run": True,
            "base_url": args.base_url,
            "requests": len(plan),
            "subscription_key": "set" if key else "absent",
            "plan": plan,
        }
    else:
        import httpx

        with httpx.Client(timeout=60.0) as client:
            results = execute(plan, client, headers or None)
        report = {"dry_run": False, "base_url": args.base_url, **summarize(results), "results": results}
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
