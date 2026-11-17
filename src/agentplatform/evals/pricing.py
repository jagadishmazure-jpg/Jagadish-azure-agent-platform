"""Illustrative token rates for the live-eval cost line.

These are a mini-class order of magnitude so an offline report can show USD per 1k tasks.
They are not a quote for ``gpt-5-mini``. Replace them from the Azure OpenAI pricing page
before citing a bill:

https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/
"""

from __future__ import annotations

INPUT_USD_PER_1M = 0.25
OUTPUT_USD_PER_1M = 2.00


def cost_per_1k_tasks(prompt_tokens: int, completion_tokens: int, tasks: int) -> float:
    """USD to judge 1,000 tasks at the illustrative rates, given the tokens one batch used."""
    if tasks <= 0:
        return 0.0
    usd = (prompt_tokens / 1_000_000) * INPUT_USD_PER_1M + (completion_tokens / 1_000_000) * OUTPUT_USD_PER_1M
    return usd * (1000 / tasks)
