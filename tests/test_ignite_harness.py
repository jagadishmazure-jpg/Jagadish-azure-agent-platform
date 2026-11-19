"""Offline Copilot harness, Toolbox MCP endpoint, and the commercial-loan approval gate."""

import pytest

from agentplatform.ignite.assumptions import ASSUMPTIONS, MATURITY, SOURCES
from agentplatform.ignite.data import CREDIT_POLICY, KnowledgeItem
from agentplatform.ignite.harness import CopilotHarness, HarnessError
from agentplatform.ignite.skills import commercial_loan_agent
from agentplatform.ignite.toolbox import TOOL_POLICIES, LoanToolbox


def _harness(knowledge=None) -> tuple[LoanToolbox, CopilotHarness]:
    toolbox = LoanToolbox()
    harness = CopilotHarness(toolbox, commercial_loan_agent(knowledge=knowledge))
    return toolbox, harness


async def test_toolbox_mcp_endpoint_lists_the_closed_tool_set():
    toolbox = LoanToolbox()
    names = await CopilotHarness(toolbox, commercial_loan_agent()).tools.list_tools()
    assert names == [
        "browser_action",
        "computer_use",
        "get_application",
        "invoke_a2a_agent",
        "open_browser_session",
        "pull_bureau",
        "record_decision",
    ]
    assert "web_search" not in names
    assert MATURITY["web_search_toolbox"] == "coming_soon"
    assert set(TOOL_POLICIES) == set(names)
    with pytest.raises(HarnessError, match="not on the toolbox"):
        await CopilotHarness(toolbox, commercial_loan_agent()).tools.call("web_search", {})


async def test_underwriting_waits_for_a_named_officer_before_booking():
    toolbox, harness = _harness()
    run = await harness.start("APP-4401")
    assert run.status == "awaiting_credit_officer"
    assert run.compute_held is False
    assert run.state["proposed_decision"] == "approve_with_conditions"
    assert run.state["policy_id"] == "CREDIT-POLICY-SMB"
    assert run.state["bureau"]["score"] == 718
    assert run.state["exposure"]["stand_in"] is True
    assert run.state["exposure"]["transport"] == "in-process"
    assert run.state["desktop"]["drove_desktop"] is False
    assert run.state["browser"]["fetched_url"] is False
    assert run.state["browser"]["isolated"] is True
    assert run.state["browser"]["recording_uri"].startswith("customer-storage://")
    assert "Insurance binder" in run.state["conditions"][0]
    assert toolbox.metrics["bookings"] == 0
    assert toolbox.metrics["hard_pulls"] == 1
    assert run.instructions == harness.definition.instructions
    with pytest.raises(HarnessError, match="named credit officer"):
        await harness.resume(run.run_id, officer_id="  ", approved=True)


async def test_approval_books_once_and_recovery_does_not_repeat_side_effects():
    toolbox, harness = _harness()
    waiting = await harness.start("APP-4401")
    before = harness.handler_runs
    recovered = await harness.recover(waiting.run_id)
    assert recovered.status == "awaiting_credit_officer"
    assert harness.handler_runs == before + 1
    assert toolbox.metrics["hard_pulls"] == 1
    assert toolbox.metrics["bookings"] == 0

    done = await harness.resume(waiting.run_id, officer_id="officer-lee", approved=True, reason="DSCR holds")
    assert done.status == "completed"
    assert done.compute_held is False
    assert done.state["booked"] is True
    assert done.state["booking"]["approved_by"] == "officer-lee"
    assert done.state["booking"]["ticket"] == "BK-APP-4401"
    assert toolbox.metrics["bookings"] == 1

    again = await harness.recover(done.run_id)
    assert again.state["booked"] is True
    assert toolbox.metrics["bookings"] == 1
    assert toolbox.metrics["hard_pulls"] == 1
    assert toolbox.dashboard()["hard_pulls"] == 1


async def test_denial_does_not_book():
    toolbox, harness = _harness()
    waiting = await harness.start("APP-4401")
    denied = await harness.resume(
        waiting.run_id, officer_id="officer-lee", approved=False, reason="Exposure is outside policy."
    )
    assert denied.status == "completed"
    assert denied.state["outcome"] == "declined"
    assert denied.state["booked"] is False
    assert denied.state["officer_reason"] == "Exposure is outside policy."
    assert toolbox.metrics["bookings"] == 0
    assert "record_decision" not in toolbox.metrics["calls"]


async def test_policy_is_supplied_by_the_bank_not_the_harness():
    strict = KnowledgeItem(id="CREDIT-POLICY-SMB", text="Board overlay.", min_dscr="99")
    _toolbox, harness = _harness(knowledge=(strict,))
    run = await harness.start("APP-4401")
    assert run.state["proposed_decision"] == "refer"
    assert "99" in run.state["conditions"][0]
    empty = CopilotHarness(LoanToolbox(), commercial_loan_agent(knowledge=()))
    with pytest.raises(HarnessError, match="does not supply knowledge"):
        await empty.start("APP-4401")


async def test_missing_consent_blocks_the_bureau_tool():
    toolbox, harness = _harness()
    with pytest.raises(HarnessError, match="no credit-pull consent"):
        await harness.start("APP-4402")
    assert toolbox.metrics["hard_pulls"] == 0
    assert toolbox.metrics["bookings"] == 0


async def test_tool_policy_blocks_a_write_without_an_officer():
    toolbox, harness = _harness()
    with pytest.raises(HarnessError, match="tool policy blocked"):
        await harness.tools.call(
            "record_decision",
            {
                "application_id": "APP-4401",
                "decision": "approve_with_conditions",
                "approved_by": "",
                "idempotency_key": "book-APP-4401",
            },
        )
    assert toolbox.metrics["blocked_by_policy"] == 1
    assert toolbox.metrics["bookings"] == 0
    assert TOOL_POLICIES["record_decision"]["requires_approval"] is True


async def test_voice_attaches_without_replacing_skills_or_booking():
    toolbox, harness = _harness()
    await harness.start("APP-4401")
    spoken = await harness.voice_turn("What is the status of APP-4401?")
    assert spoken["maturity"] == "ga"
    assert spoken["telephony"] == "native"
    assert spoken["barged_in"] is False
    assert "credit officer" in spoken["reply"]
    assert spoken["skills"] == harness.definition.skill_names()
    assert spoken["bookings"] == 0
    interrupted = await harness.voice_turn("wait, different question", interrupt=True)
    assert interrupted["barged_in"] is True
    assert interrupted["reply"] == ""
    assert toolbox.metrics["bookings"] == 0
    assert harness.definition.voice_enabled is False


async def test_browser_take_control_pauses_without_fetching_a_url():
    toolbox, harness = _harness()
    run = await harness.request_browser_take_control("vault login")
    assert run.status == "awaiting_browser_oversight"
    assert run.compute_held is False
    assert run.state["isolated"] is True
    assert run.state["fetched_url"] is False
    assert run.state["browser"]["take_control_required"] is True
    assert run.state["browser"]["live_view"] is True
    assert run.state["recording_uri"] == "customer-storage://recordings/br-vault-login"
    session = toolbox.sessions["br-vault-login"]
    assert session["private_network_access"] == "preview"
    assert session["maturity"] == "ga"
    assert toolbox.metrics["bookings"] == 0


async def test_egress_is_blocked_outside_the_sandbox():
    _toolbox, harness = _harness()
    with pytest.raises(HarnessError, match="blocked outside the sandbox"):
        harness.sandbox.enforce_egress("investor.example")
    assert harness.sandbox.blocked_hosts == ["investor.example"]
    assert MATURITY["hosted_agent_egress_controls"] == "ga"
    assert MATURITY["copilot_harness"] == "public_preview"


def test_sources_mark_ga_capabilities_and_list_assumptions():
    assert SOURCES["foundry_agent_service_ignite_2026"].endswith(
        "whats-new-in-foundry-agent-service-at-ignite-2026/"
    )
    assert "durable-agents-microsoft-agent-framework" in SOURCES["durable_task_microsoft_agent_framework"]
    for name in ("voice", "a2a_tool", "computer_use", "browser_automation", "durable_task_extension"):
        assert MATURITY[name] == "ga"
    text = " ".join(ASSUMPTIONS)
    assert "two authoring choices" in text
    assert "not re-executed" in text
    assert "billing API" in text
    assert CREDIT_POLICY.min_dscr == "1.25"
