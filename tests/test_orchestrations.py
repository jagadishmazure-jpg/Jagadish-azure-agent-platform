"""The five MAF prebuilt orchestrations over the loan-conditions scenario (offline, deterministic)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from agent_framework import Agent
from agent_framework.orchestrations import AgentRequestInfoResponse, HandoffBuilder

from agentplatform.llm.clients import MockChatClient
from agentplatform.orchestrations import compare, concurrent, group_chat, handoff, magentic, sequential
from agentplatform.orchestrations.facts import expected_flags, gather_facts
from agentplatform.orchestrations.roles import Roster

logging.getLogger("agent_framework").setLevel(logging.ERROR)

EXPECTED = {
    "L-1001": (["recent_inquiry", "unsourced_deposit"], "approve_with_conditions"),
    "L-1002": (["declining_income", "dti_over_limit"], "refer"),
    "L-1003": (["dti_over_limit"], "refer"),
}


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("loan", sorted(EXPECTED))
def test_facts_come_from_the_data_plane(loan):
    facts = run(gather_facts(loan))
    assert expected_flags(facts) == EXPECTED[loan][0]
    assert facts["credit"]["report_id"].startswith(f"CR-{facts['borrower_id']}")


@pytest.mark.parametrize("pattern", sorted(compare.PATTERNS))
@pytest.mark.parametrize("loan", sorted(EXPECTED))
def test_every_pattern_reaches_the_rule_answer(pattern, loan):
    r = run(compare.PATTERNS[pattern](loan))
    assert (r.conditions, r.decision) == EXPECTED[loan]
    assert r.exact and r.recall == 1.0


def test_sequential_pauses_after_underwriter_and_accepts_feedback():
    answers = iter(
        [AgentRequestInfoResponse.from_strings(["ADD: low_reserves"]), AgentRequestInfoResponse.approve()]
    )
    r = run(sequential.run("L-1001", review=lambda _req: next(answers)))
    assert r.hitl_requests == ["AgentExecutorResponse", "AgentExecutorResponse"]
    assert "low_reserves" in r.conditions  # the human's addition reached the re-run underwriter


def test_sequential_resumes_from_checkpoint_in_a_fresh_graph():
    r = run(sequential.run("L-1003", restart=True))
    assert r.extra["restarted"] and r.exact and r.hitl_requests == ["AgentExecutorResponse"]


def test_concurrent_missing_lane_refers_instead_of_approving():
    r = run(concurrent.run("L-1001", faults={"assets_down"}))
    assert r.decision == "refer" and r.stop_reason == "missing_lanes"
    assert r.llm_calls == 5  # income + credit (tool call + answer each) + one empty assets answer


def test_handoff_routes_only_to_lanes_with_findings():
    r = run(handoff.run("L-1003"))
    assert r.extra["handoffs"] == [("triage", "credit"), ("credit", "underwriter")]
    assert {a for a, _ in r.turns} == {"triage", "credit", "underwriter"}


def test_handoff_asks_the_human_when_the_loan_id_is_missing():
    r = run(handoff.run("L-1002", prompt="Please review this file."))
    assert r.hitl_requests == ["HandoffAgentUserRequest"]
    assert r.turns[0][0] == "triage" and "loan id" in r.turns[0][1]
    assert r.exact


def test_handoff_dead_end_stays_with_the_human():
    r = run(handoff.run("L-1001", faults={"assets_down"}))
    assert r.decision is None and r.stop_reason == "awaiting_user"


def test_handoff_builder_requires_history_persistence_flag():
    agents = [Agent(client=MockChatClient(), name=n, instructions="x", description="x") for n in ("a", "b")]
    with pytest.raises(ValueError, match="require_per_service_call_history_persistence"):
        HandoffBuilder(participants=agents).with_start_agent(agents[0]).build()


def test_group_chat_round_cap_is_a_safe_stop():
    r = run(group_chat.run("L-1001", faults={"looping_reviewer"}))
    assert r.stop_reason == "max_rounds_unapproved" and r.decision == "refer"
    assert r.extra["rounds"] == group_chat.MAX_ROUNDS


def test_group_chat_checker_catches_a_missing_lane():
    r = run(group_chat.run("L-1001", faults={"assets_down"}))
    assert r.decision == "refer" and "unsourced_deposit" in r.conditions  # reviewer supplied it


def test_group_chat_agent_orchestrator_costs_one_call_per_round():
    func = run(group_chat.run("L-1002", selection="func"))
    agent = run(group_chat.run("L-1002", selection="agent"))
    assert agent.llm_calls - func.llm_calls == func.extra["rounds"]


def test_magentic_plan_review_revise_then_approve():
    r = run(magentic.run("L-1001", review=magentic.revise_once("Check assets before credit.")))
    assert r.hitl_requests == ["MagenticPlanReviewRequest", "MagenticPlanReviewRequest"] and r.exact


def test_magentic_stall_resets_replans_and_carries_the_failed_lane():
    r = run(magentic.run("L-1001", faults={"assets_down"}))
    assert "REPLANNED" in r.extra["events"]
    assert r.decision == "refer" and "MISSING_LANES: assets" in r.final_text


def test_magentic_round_cap_terminates():
    r = run(magentic.run("L-1001", max_rounds=2))
    assert r.stop_reason == "limit_reached" and r.decision == "refer"


def test_roster_numbers_only_come_from_tools():
    roster = Roster(run(gather_facts("L-1002")))
    agent = roster.agent("credit")
    assert [t.name for t in agent.default_options["tools"]] == ["get_credit_facts"]


def test_comparison_doc_is_fresh():
    from scripts.orchestrations_demo import main

    assert main(["--compare", "--check"]) == 0
