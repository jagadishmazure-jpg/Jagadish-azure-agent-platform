"""Offline Copilot harness, Toolbox MCP endpoint, and the loan-commitment approval gate."""

from datetime import date

import pytest

from agentplatform.foundry_harness.harness import HARNESS_TYPE, select_in_force
from agentplatform.foundry_harness.loan import (
    APPLICATIONS,
    DEFINITION_PATH,
    GUIDELINES,
    PROJECT_ENDPOINT,
    TOOLBOX_NAME,
    build_lending_toolbox,
    load_agent_definition,
    load_skill,
    rule_decision,
    start_loan_review,
)
from agentplatform.foundry_harness.models import Sandbox, SkillRef, ToolboxTool
from agentplatform.foundry_harness.toolbox import PREVIEW_TOOL_POLICIES

MARCH = date(2025, 3, 1)
SEPTEMBER = date(2025, 9, 1)


def _names(service, url: str) -> list[str]:
    return [item["name"] for item in service.tools_list(url)]


def test_harness_loads_the_skill_and_refuses_shell():
    harness, run = start_loan_review("L-2001", MARCH, behavior="shell")
    assert harness.skill.name == "underwrite-file"
    assert "queue_commitment" in harness.skill.body
    assert run.status == "refused"
    assert run.answer == "sandbox refused shell"
    assert harness.toolbox.call_log == []
    assert run.writes == []


def test_unknown_tool_is_refused_and_not_called():
    _, run = start_loan_review("L-2001", MARCH, behavior="unknown")
    assert run.status == "refused"
    assert run.answer == "tool wire_funds is not in the toolbox"
    assert run.writes == []


def test_toolbox_consumer_endpoint_follows_the_default_version():
    service, consumer = build_lending_toolbox()
    pinned = service.developer_endpoint(TOOLBOX_NAME, "1")
    assert consumer == (f"{PROJECT_ENDPOINT}/toolboxes/{TOOLBOX_NAME}/mcp?api-version=v1")
    assert service.default_version(TOOLBOX_NAME) == "1"
    assert _names(service, consumer) == ["get_application", "queue_commitment"]

    def reserves(_: dict) -> dict:
        return {"months": 6}

    service.create_version(
        TOOLBOX_NAME,
        description="Adds a reserves read.",
        tools=[
            *service.resolve(pinned).tools,
            ToolboxTool("get_reserves", "Read reserve months.", {"type": "object"}, "never", reserves),
        ],
        skills=[SkillRef("underwrite-file")],
        policies=PREVIEW_TOOL_POLICIES,
    )
    assert service.default_version(TOOLBOX_NAME) == "1"
    assert "get_reserves" not in _names(service, consumer)
    service.promote(TOOLBOX_NAME, "2")
    assert _names(service, consumer) == ["get_application", "queue_commitment", "get_reserves"]
    assert "get_reserves" not in _names(service, pinned)
    listed = {item["name"]: item for item in service.tools_list(consumer)}
    assert listed["queue_commitment"]["_meta"]["tool_configuration"]["require_approval"] == "always"
    assert listed["get_application"]["_meta"]["tool_configuration"]["require_approval"] == "never"
    assert service.resolve(consumer).policies["status"] == "[verify]"


def test_mcp_endpoint_does_not_enforce_approval_the_harness_does():
    service, url = build_lending_toolbox()
    direct = service.tools_call(
        url,
        "queue_commitment",
        {
            "loan_id": "L-2001",
            "decision": "conditionally_approved",
            "citation": "GL-DTI-200.v1",
            "idempotency_key": "direct-key",
        },
    )
    assert direct["ticket"] == "CMT-L-2001" and direct["duplicate"] is False
    again = service.tools_call(
        url,
        "queue_commitment",
        {
            "loan_id": "L-2001",
            "decision": "conditionally_approved",
            "citation": "GL-DTI-200.v1",
            "idempotency_key": "direct-key",
        },
    )
    assert again["duplicate"] is True and again["ticket"] == direct["ticket"]

    harness, run = start_loan_review("L-2001", MARCH)
    assert run.status == "awaiting_approval"
    assert run.pending_tool == "queue_commitment"
    assert [entry[2] for entry in harness.toolbox.call_log] == ["get_application"]
    done = harness.resume(run, approved=True, approver="uw-1")
    assert done.status == "completed"
    assert done.writes[0]["duplicate"] is False
    assert [entry[2] for entry in harness.toolbox.call_log].count("queue_commitment") == 1
    assert done.citation_ids == ["GL-DTI-200.v1"]
    assert "underwrite-file" in harness.model.contexts[0]
    assert "GL-DTI-200.v1" in harness.model.contexts[0]
    assert "GL-DTI-200.v2" not in harness.model.contexts[0]


def test_denied_approval_does_not_queue_a_commitment():
    harness, run = start_loan_review("L-2001", MARCH)
    done = harness.resume(run, approved=False, approver="uw-1")
    assert done.status == "completed"
    assert done.writes == []
    assert "not queued" in done.answer
    assert "queue_commitment" not in [entry[2] for entry in harness.toolbox.call_log]


def test_approval_requires_a_named_person():
    harness, run = start_loan_review("L-2001", MARCH)
    with pytest.raises(RuntimeError, match="named approver"):
        harness.resume(run, approved=True, approver="  ")
    assert harness.toolbox.call_log[-1][2] == "get_application"


def test_guideline_is_as_of_the_application_date():
    assert rule_decision(APPLICATIONS["L-2003"], select_in_force(GUIDELINES, MARCH)) == (
        "refer",
        "GL-DTI-200.v1",
    )
    assert rule_decision(APPLICATIONS["L-2003"], select_in_force(GUIDELINES, SEPTEMBER)) == (
        "conditionally_approved",
        "GL-DTI-200.v2",
    )
    assert [item.id for item in select_in_force(GUIDELINES, date(2025, 6, 30))] == ["GL-DTI-200.v1"]
    assert [item.id for item in select_in_force(GUIDELINES, date(2025, 7, 1))] == ["GL-DTI-200.v2"]

    referred_harness, referred = start_loan_review("L-2003", MARCH)
    assert referred.status == "completed"
    assert referred.writes == []
    assert referred.citation_ids == ["GL-DTI-200.v1"]
    assert "GL-DTI-200.v2" not in referred_harness.model.contexts[0]

    approved_harness, waiting = start_loan_review("L-2003", SEPTEMBER)
    assert waiting.pending_arguments["citation"] == "GL-DTI-200.v2"
    assert "GL-DTI-200.v1" not in approved_harness.model.contexts[0]
    done = approved_harness.resume(waiting, approved=True, approver="uw-2")
    assert done.citation_ids == ["GL-DTI-200.v2"]
    assert done.writes[0]["ticket"] == "CMT-L-2003"


def test_stale_citation_is_refused():
    _, run = start_loan_review("L-2001", MARCH, behavior="stale_citation")
    assert run.status == "refused"
    assert run.answer == "citation GL-DTI-200.v2 is not in force"
    assert run.writes == []


def test_step_budget_stops_before_the_write():
    harness, run = start_loan_review("L-2001", MARCH, sandbox=Sandbox(max_steps=1))
    assert run.status == "stopped"
    assert run.answer == "step budget exhausted"
    assert run.writes == []
    assert [entry[2] for entry in harness.toolbox.call_log] == ["get_application"]


def test_agent_definition_marks_the_preview_harness():
    definition = load_agent_definition()
    skill = load_skill()
    assert definition["harness_type"] == HARNESS_TYPE == "microsoft_copilot_preview"
    assert definition["preview"] == "true"
    assert definition["verify"].startswith("[verify]")
    text = DEFINITION_PATH.read_text()
    assert definition["skill"] == skill.name == "underwrite-file"
    assert definition["toolbox"] == TOOLBOX_NAME
    assert "public preview" in text
    assert "[verify]" in text
