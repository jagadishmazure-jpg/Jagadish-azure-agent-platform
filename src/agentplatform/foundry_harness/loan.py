"""Regulated loan-commitment sample on the offline Copilot harness.

The rule function owns the DTI decision. The model only proposes the next tool or a
cited final answer, and ``queue_commitment`` cannot run until a named person approves.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from agentplatform.foundry_harness.harness import CopilotHarness, ScriptedModel, select_in_force
from agentplatform.foundry_harness.models import (
    HarnessRun,
    KnowledgePassage,
    ModelAction,
    Sandbox,
    Skill,
    SkillRef,
    ToolboxTool,
)
from agentplatform.foundry_harness.toolbox import PREVIEW_TOOL_POLICIES, MockToolboxService

PROJECT_ENDPOINT = "https://example.services.ai.azure.com/api/projects/demo"
TOOLBOX_NAME = "lending-toolbox"
SKILL_PATH = Path(__file__).resolve().parent / "skills" / "underwrite-file" / "SKILL.md"
DEFINITION_PATH = Path(__file__).resolve().parent / "definitions" / "loan-review.agent.yaml"

APPLICATIONS: dict[str, dict[str, Any]] = {
    "L-2001": {"loan_id": "L-2001", "dti": 0.41, "reserves_months": 4, "product": "conventional"},
    "L-2002": {"loan_id": "L-2002", "dti": 0.52, "reserves_months": 1, "product": "conventional"},
    "L-2003": {"loan_id": "L-2003", "dti": 0.48, "reserves_months": 8, "product": "conventional"},
}

GUIDELINES: list[KnowledgePassage] = [
    KnowledgePassage(
        "GL-DTI-200.v1",
        "Maximum DTI is 45 percent for conventional loans.",
        date(2024, 1, 1),
        date(2025, 6, 30),
        {"dti_cap": 0.45},
    ),
    KnowledgePassage(
        "GL-DTI-200.v2",
        "Maximum DTI is 45 percent, or 50 percent when reserves cover at least 6 months.",
        date(2025, 7, 1),
        None,
        {"dti_cap": 0.45, "dti_cap_with_reserves": 0.50, "reserves_offset_months": 6},
    ),
]


def load_skill(path: Path = SKILL_PATH) -> Skill:
    text = path.read_text()
    name = _scalar(text, "name")
    description = _scalar(text, "description")
    body = text.split("---", 2)[-1].strip()
    return Skill(name=name, description=description, body=body)


def load_agent_definition(path: Path = DEFINITION_PATH) -> dict[str, str]:
    """Source-controlled prompt-agent definition.

    [verify] ``microsoft_copilot_preview`` is the public-preview harness type. Switching
    the harness after creation is not supported on the real service.
    """
    text = path.read_text()
    harness_type = _scalar(text, "type")
    return {
        "name": _scalar(text, "agent_name"),
        "kind": _scalar(text, "kind"),
        "harness_type": harness_type,
        "model": _scalar(text, "model"),
        "skill": _scalar(text, "skill"),
        "toolbox": _scalar(text, "toolbox"),
        "preview": "true" if harness_type.endswith("_preview") else "false",
        "verify": "[verify] microsoft_copilot_preview is public preview and is not in the pinned SDKs",
    }


def rule_decision(application: dict[str, Any], passages: list[KnowledgePassage]) -> tuple[str, str]:
    """DTI outcome from guideline params. The model is not asked to do this arithmetic."""
    if not passages:
        raise ValueError("no guideline is in force")
    passage = max(passages, key=lambda item: item.effective_from)
    cap = passage.params["dti_cap"]
    offset_at = passage.params.get("reserves_offset_months")
    if offset_at is not None and application["reserves_months"] >= offset_at:
        cap = passage.params["dti_cap_with_reserves"]
    decision = "conditionally_approved" if application["dti"] <= cap else "refer"
    return decision, passage.id


def plan_for(loan_id: str, as_of: date, *, behavior: str = "rule") -> list[ModelAction]:
    application = APPLICATIONS[loan_id]
    if behavior == "shell":
        return [ModelAction("tool", "shell", {"command": "uname"})]
    if behavior == "unknown":
        return [ModelAction("tool", "wire_funds", {"loan_id": loan_id, "amount": 1})]
    if behavior == "stale_citation":
        return [
            ModelAction("tool", "get_application", {"loan_id": loan_id}),
            ModelAction("final", text="Using a guideline outside its window.", citation="GL-DTI-200.v2"),
        ]
    decision, citation = rule_decision(application, select_in_force(GUIDELINES, as_of))
    steps = [ModelAction("tool", "get_application", {"loan_id": loan_id})]
    if decision == "conditionally_approved":
        steps.append(
            ModelAction(
                "tool",
                "queue_commitment",
                {"loan_id": loan_id, "decision": decision, "citation": citation},
            )
        )
        steps.append(ModelAction("final", text=f"Commitment queued under {citation}.", citation=citation))
    else:
        steps.append(
            ModelAction("final", text=f"Referred under {citation}. No commitment queued.", citation=citation)
        )
    return steps


def build_lending_toolbox(service: MockToolboxService | None = None) -> tuple[MockToolboxService, str]:
    service = service or MockToolboxService(PROJECT_ENDPOINT)

    def get_application(arguments: dict[str, Any]) -> dict[str, Any]:
        return dict(APPLICATIONS[arguments["loan_id"]])

    def queue_commitment(arguments: dict[str, Any]) -> dict[str, Any]:
        key = arguments["idempotency_key"]
        existing = service.ledger.get(key)
        if existing is not None:
            return {**existing, "duplicate": True}
        ticket = {
            "ticket": f"CMT-{arguments['loan_id']}",
            "decision": arguments["decision"],
            "citation": arguments["citation"],
            "duplicate": False,
        }
        service.ledger[key] = ticket
        return dict(ticket)

    service.create_version(
        TOOLBOX_NAME,
        description="Shared lending tools for commitment review.",
        tools=[
            ToolboxTool(
                "get_application",
                "Read the synthetic loan application.",
                {"type": "object", "properties": {"loan_id": {"type": "string"}}, "required": ["loan_id"]},
                "never",
                get_application,
            ),
            ToolboxTool(
                "queue_commitment",
                "Queue a commitment. Requires a named human approval.",
                {
                    "type": "object",
                    "properties": {
                        "loan_id": {"type": "string"},
                        "decision": {"type": "string"},
                        "citation": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["loan_id", "decision", "citation"],
                },
                "always",
                queue_commitment,
            ),
        ],
        skills=[SkillRef("underwrite-file")],
        policies=PREVIEW_TOOL_POLICIES,
    )
    return service, service.consumer_endpoint(TOOLBOX_NAME)


def start_loan_review(
    loan_id: str,
    as_of: date,
    *,
    behavior: str = "rule",
    sandbox: Sandbox | None = None,
    service: MockToolboxService | None = None,
    toolbox_url: str | None = None,
) -> tuple[CopilotHarness, HarnessRun]:
    if service is None or toolbox_url is None:
        service, toolbox_url = build_lending_toolbox(service)
    harness = CopilotHarness(
        skill=load_skill(),
        knowledge=GUIDELINES,
        toolbox=service,
        toolbox_url=toolbox_url,
        model=ScriptedModel(plan_for(loan_id, as_of, behavior=behavior)),
        sandbox=sandbox,
    )
    run = harness.start(f"Review {loan_id} for a commitment decision.", as_of=as_of)
    return harness, run


def _scalar(text: str, key: str) -> str:
    match = re.search(rf"^[ \t]*{key}:\s*(.+?)\s*$", text, re.M)
    if match is None:
        raise ValueError(f"{key} is missing")
    return match.group(1)
