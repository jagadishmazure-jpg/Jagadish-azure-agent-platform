"""Value types for the offline Copilot harness and Toolbox mocks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Skill:
    """A reusable procedure. The harness loads it; the caller writes it."""

    name: str
    description: str
    body: str


@dataclass(frozen=True)
class KnowledgePassage:
    """A guideline the developer supplies. The harness, not the model, applies the as-of filter."""

    id: str
    text: str
    effective_from: date
    effective_to: date | None
    params: dict[str, float]


@dataclass(frozen=True)
class SkillRef:
    name: str
    version: str = ""


@dataclass(frozen=True)
class ToolboxTool:
    """One tool inside a toolbox version.

    ``require_approval`` is ``always`` or ``never``, matching the Learn toolbox contract.
    The MCP endpoint records the value and does not enforce it. The harness does.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    require_approval: str
    handler: ToolHandler


@dataclass(frozen=True)
class Sandbox:
    """What the managed harness allows. Foundry operates this boundary in the real service."""

    allow_shell: bool = False
    allow_web_fetch: bool = False
    allow_files: bool = False
    allow_subagents: bool = False
    max_steps: int = 8


@dataclass(frozen=True)
class ModelAction:
    """One step the model proposes. The harness decides whether it may run."""

    action: str
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    citation: str = ""


@dataclass
class HarnessRun:
    status: str
    answer: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)
    pending_tool: str = ""
    pending_arguments: dict[str, Any] = field(default_factory=dict)
    citation_ids: list[str] = field(default_factory=list)
    writes: list[dict[str, Any]] = field(default_factory=list)
