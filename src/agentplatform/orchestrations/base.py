"""Result type and helpers shared by the five orchestration modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent_framework import AgentResponse, WorkflowRunResult

from agentplatform.orchestrations.roles import CONDITIONS_RE, DECISION_RE, parse_list


@dataclass
class OrchestrationRun:
    pattern: str
    loan_id: str
    final_text: str
    expected: list[str]
    llm_calls: int = 0
    turns: list[tuple[str, str]] = field(default_factory=list)  # (author, text) of agent messages
    hitl_requests: list[str] = field(default_factory=list)  # request payload type names, in order
    stop_reason: str = "completed"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def conditions(self) -> list[str]:
        return sorted(set(parse_list(CONDITIONS_RE, self.final_text)))

    @property
    def decision(self) -> str | None:
        m = DECISION_RE.search(self.final_text or "")
        return m.group(1) if m else None

    @property
    def recall(self) -> float:
        if not self.expected:
            return 1.0 if self.decision == "approve" else 0.0
        return len(set(self.expected) & set(self.conditions)) / len(self.expected)

    @property
    def exact(self) -> bool:
        return self.decision is not None and self.conditions == sorted(self.expected)

    def summary(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(conditions=self.conditions, decision=self.decision, recall=self.recall, exact=self.exact)
        return d


def responses(result: WorkflowRunResult) -> list[AgentResponse]:
    return [o for o in result.get_outputs() if isinstance(o, AgentResponse)]


def turns_of(outputs: list[AgentResponse]) -> list[tuple[str, str]]:
    return [
        (m.author_name or "?", m.text)
        for r in outputs
        for m in r.messages
        if m.role == "assistant" and m.text
    ]
