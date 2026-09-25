import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from agent_framework import ChatResponse, Message

from agentplatform.harness.identity import Principal, new_traceparent, trace_id_of
from agentplatform.harness.killswitch import KILL_SWITCH
from agentplatform.harness.outbox import InMemoryOutbox
from agentplatform.knowledge import InMemoryHybridSearch, load_corpus
from agentplatform.llm import MockChatClient
from agentplatform.mcp_servers import credit_bureau, los
from agentplatform.mortgage.agents import AgentSuite
from agentplatform.mortgage.models import UnderwriterDecision
from agentplatform.mortgage.service import UnderwritingService, make_checkpoint_storage
from agentplatform.mortgage.workflow import Deps

logging.getLogger("agent_framework").setLevel(logging.WARNING)
UW = Principal("uw-jane", "contoso-mortgage", frozenset({"underwriting"}))
SENIOR = Principal("uw-sr", "contoso-mortgage", frozenset({"underwriting", "underwriting-senior"}))


def svc(**deps_kw) -> UnderwritingService:
    return UnderwritingService(deps=Deps(**deps_kw), storage=make_checkpoint_storage(in_memory=True))


def ids(rec):
    return {c["id"] for c in rec.review["conditions"]}


async def test_happy_path_every_condition_cites_in_force_guideline():
    s = svc()
    tp = new_traceparent()
    rec = await s.start("L-1001", UW, tp)
    assert rec.status == "awaiting_underwriter"
    r = rec.review
    assert r["recommendation"] == "approved_with_conditions"
    assert ids(rec) == {"C-INC-VVOE", "C-AST-LD1", "C-CR-INQ", "C-PRP-APR"}
    assert all(c["guideline_ids"] for c in r["conditions"]) and r["critic"]["passed"]
    assert r["capacity"]["dti_rule"] == "GL-DTI-200.v2" and r["capacity"]["score_rule"] == "GL-CR-100.v1"
    rec = await s.decide(rec.run_id, UnderwriterDecision(True, "uw-jane"))
    out = rec.outcome
    assert out["status"] == "decision_issued" and out["letter"]["decision"] == "approved_with_conditions"
    assert out["los_ticket"]["status"] == "conditionally_approved"
    assert out["trace_id"] == trace_id_of(tp)  # trace stitched end to end
    assert set(out["exits"]) >= {"intake", "income", "credit", "knowledge", "critic", "decision_letter"}


async def test_temporal_rag_applies_guideline_in_force_on_application_date():
    rec = await svc().start("L-1002", UW)  # applied 2025-03-10: DTI max 45% (v1), no reserves extension
    cap = rec.review["capacity"]
    assert cap["dti_rule"] == "GL-DTI-200.v1" and cap["dti"] > 0.45
    assert rec.review["recommendation"] == "referred"  # never an automated denial
    assert "C-INC-LOE" in ids(rec) and "C-DOC-L-1002-bank" in ids(rec)  # declining income + OCR confidence


async def test_graph_rag_and_acl_overlay():
    rec = await svc().start("L-1003", UW)
    assert "C-PRP-NAL" in ids(rec) and "C-OVL-INV" not in ids(rec)
    assert rec.review["capacity"]["score_rule"] == "GL-CR-100.v2"
    senior = await svc().start("L-1003", SENIOR)  # confidential overlay visible only to senior UW group
    assert "C-OVL-INV" in ids(senior)


async def test_hitl_deny_stops_before_any_write():
    s = svc()
    before = len(los.QUEUED)
    rec = await s.start("L-1001", UW)
    rec = await s.decide(rec.run_id, UnderwriterDecision(False, "uw-jane", "need updated appraisal first"))
    assert rec.status == "returned_to_processing" and rec.outcome["letter"] is None
    assert len(los.QUEUED) == before


async def test_resume_from_checkpoint_after_restart(tmp_path):
    from agent_framework import FileCheckpointStorage

    from agentplatform.mortgage.models import CHECKPOINT_TYPES

    storage = FileCheckpointStorage(tmp_path, allowed_checkpoint_types=CHECKPOINT_TYPES)
    s1 = UnderwritingService(deps=Deps(), storage=storage)
    rec = await s1.start("L-1003", UW)
    run_id = rec.run_id
    # "process restart": new service, new graph instances, same durable checkpoints
    s2 = UnderwritingService(deps=Deps(), storage=storage)
    rec2 = await s2.resume(run_id)
    assert rec2.status == "awaiting_underwriter" and rec2.review["loan_id"] == "L-1003"
    rec2 = await s2.decide(run_id, UnderwriterDecision(True, "uw-jane"))
    assert rec2.status == "decision_issued"


async def test_kill_switch_halts_between_nodes():
    s = svc()
    rec = await s.start("L-1001", UW)
    KILL_SWITCH.trip(agent="mortgage-underwriting")
    rec = await s.decide(rec.run_id, UnderwriterDecision(True))
    assert rec.status == "halted" and rec.outcome["letter"] is None


async def test_search_outage_degrades_to_limited_and_suspends():
    search = InMemoryHybridSearch(load_corpus())
    search.fail_next = 3
    rec = await svc(search=search).start("L-1001", UW)
    assert rec.review["limited"] is True
    assert rec.review["recommendation"] == "suspended"
    assert any("LIMITED" in i for i in rec.review["issues"])


async def test_credit_bureau_outage_escalates_no_decision():
    credit_bureau.STATS["fail_next"] = 3
    rec = await svc().start("L-1001", UW)
    credit_bureau.STATS["fail_next"] = 0
    assert rec.review["recommendation"] == "suspended"
    assert any("bureau unavailable" in i for i in rec.review["issues"])


async def test_bureau_retry_reuses_request_id_no_double_pull():
    credit_bureau.STATS["fail_next"] = 1
    before = credit_bureau.STATS["hard_pulls"]
    rec = await svc().start("L-1001", UW)
    assert rec.review["recommendation"] == "approved_with_conditions"
    assert credit_bureau.STATS["hard_pulls"] == before + 1


async def test_model_outage_degrades_to_deterministic_drafts():
    agents = AgentSuite(client=MockChatClient(fail_times=10_000))
    s = svc(agents=agents)
    rec = await s.start("L-1001", UW)
    assert rec.review["recommendation"] == "approved_with_conditions"  # numbers never came from the LLM
    assert "conditions" in agents.degraded and "income" in agents.degraded


def _rogue_conditions(text: str):
    def script(messages, options):
        fmt = options.get("response_format")
        if fmt is None or fmt.__name__ != "ConditionSet":
            return None
        payload = json.loads(messages[-1].text.split("```json", 1)[1].split("```", 1)[0])
        conds = payload["draft"]["conditions"] + [
            {
                "id": "C-LLM-1",
                "category": "credit",
                "text": text,
                "timing": "PTD",
                "guideline_ids": [],
                "source_agent": "conditions-agent",
            }
        ]
        return ChatResponse(
            messages=[Message(role="assistant", contents=[json.dumps({"conditions": conds})])]
        )

    return script


async def test_critic_repairs_uncited_condition_with_agentic_rag():
    agents = AgentSuite(
        client=MockChatClient(
            script=_rogue_conditions(
                "Borrower letter of explanation for derogatory Chapter 7 bankruptcy seasoning"
            )
        )
    )
    rec = await svc(agents=agents).start("L-1001", UW)
    c = next(c for c in rec.review["conditions"] if c["id"] == "C-LLM-1")
    assert c["guideline_ids"] == ["GL-CR-130.v1"]
    assert rec.review["critic"]["passed"] and rec.review["critic"]["repairs"] == 1


async def test_critic_drops_uncitable_condition_and_escalates():
    agents = AgentSuite(
        client=MockChatClient(script=_rogue_conditions("Provide a photo of the borrower's pet zebra"))
    )
    rec = await svc(agents=agents).start("L-1001", UW)
    assert "C-LLM-1" not in ids(rec)
    assert [c["id"] for c in rec.review["critic"]["dropped"]] == ["C-LLM-1"]
    assert any("critic failed" in i for i in rec.review["issues"])


async def test_outbox_failure_compensates():
    outbox = InMemoryOutbox(fail_next=1)
    s = svc(outbox=outbox)
    rec = await s.start("L-1001", UW)
    rec = await s.decide(rec.run_id, UnderwriterDecision(True))
    assert rec.status == "in_review" and rec.outcome["exits"]["decision_letter"] == "compensate"
    assert los.QUEUED[f"{rec.run_id}:approved_with_conditions:compensate"]["status"] == "in_review"
    assert not outbox.messages


async def test_hitl_sla_timeout_auto_denies():
    s = svc()
    rec = await s.start("L-1001", UW)
    expired = await s.expire_reviews(datetime.now(UTC) + timedelta(hours=25))
    assert expired == [rec.run_id] and s.runs[rec.run_id].status == "returned_to_processing"


async def test_unknown_loan_rejected():
    rec = await svc().start("L-9999", UW)
    assert rec.status == "rejected"


@pytest.mark.parametrize("loan", ["L-1001", "L-1003"])
async def test_decision_letter_lists_only_approved_conditions(loan):
    s = svc()
    rec = await s.start(loan, UW)
    rec = await s.decide(rec.run_id, UnderwriterDecision(True, remove_condition_ids=["C-PRP-APR"]))
    letter = rec.outcome["letter"]
    assert "C-PRP-APR" not in {c["id"] for c in letter["conditions"]}
    assert set(letter["citations"]) == {g for c in letter["conditions"] for g in c["guideline_ids"]}
