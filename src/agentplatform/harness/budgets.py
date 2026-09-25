"""Stop conditions: max steps, max tool calls, max identical calls, max cost, max writes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"budget exceeded: {kind} ({detail})")
        self.kind = kind


@dataclass
class Budget:
    max_steps: int = 40
    max_tool_calls: int = 30
    max_identical_calls: int = 2
    max_cost_usd: float = 0.50
    max_writes: int = 2
    steps: int = 0
    tool_calls: int = 0
    writes: int = 0
    cost_usd: float = 0.0
    _seen: dict[str, int] = field(default_factory=dict)

    def step(self, node: str) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise BudgetExceeded("max_steps", node)

    def tool(self, name: str, args: dict | None = None, *, write: bool = False) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceeded("max_tool_calls", name)
        key = f"{name}:{json.dumps(args or {}, sort_keys=True, default=str)}"
        self._seen[key] = self._seen.get(key, 0) + 1
        if self._seen[key] > self.max_identical_calls:
            raise BudgetExceeded("max_identical_calls", key)
        if write:
            self.writes += 1
            if self.writes > self.max_writes:
                raise BudgetExceeded("max_writes", name)

    def spend(self, usd: float) -> None:
        self.cost_usd += usd
        if self.cost_usd > self.max_cost_usd:
            raise BudgetExceeded("max_cost_usd", f"{self.cost_usd:.4f}")

    def snapshot(self) -> dict:
        return {
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "writes": self.writes,
            "cost_usd": round(self.cost_usd, 6),
        }
