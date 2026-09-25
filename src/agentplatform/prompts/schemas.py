"""Output contracts. Any step that feeds a write, a letter, or a critic must return one of these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Narrative(BaseModel):
    summary: str
    citations: list[str] = Field(default_factory=list)


class ConditionOut(BaseModel):
    id: str
    category: Literal["income", "assets", "credit", "property", "identity", "documentation", "compliance"]
    text: str
    timing: Literal["PTD", "PTF", "PTC"] = "PTD"  # prior to docs / funding / closing
    guideline_ids: list[str] = Field(default_factory=list)
    source_agent: str


class ConditionSet(BaseModel):
    conditions: list[ConditionOut]


class CriticReport(BaseModel):
    passed: bool
    uncited: list[str] = Field(default_factory=list)
    not_in_force: list[str] = Field(default_factory=list)
    not_in_evidence: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DecisionLetter(BaseModel):
    loan_id: str
    decision: Literal["approved_with_conditions", "suspended", "referred"]
    body: str
    conditions: list[ConditionOut]
    citations: list[str]


class PolicyAnswer(BaseModel):
    answer: str
    citations: list[str]
    limited: bool = False


class TicketTriage(BaseModel):
    category: str
    priority: Literal["P1", "P2", "P3", "P4"]
    next_action: str
    requires_approval: bool = False
    citations: list[str] = Field(default_factory=list)
