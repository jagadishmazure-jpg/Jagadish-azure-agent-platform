import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from agentplatform.a2a.agents import HANDLERS
from agentplatform.a2a.cards import CONTROL_PLANE_EXT, AgentSpec, SkillSpec, card_json
from agentplatform.a2a.catalog import CATALOG, spec_by_id
from agentplatform.a2a.client import A2AError
from agentplatform.a2a.local import local_apps, local_client
from agentplatform.a2a.registry import DIRECTORY
from agentplatform.a2a.server import create_a2a_app
from agentplatform.harness.identity import Principal, new_traceparent, trace_id_of

logging.getLogger("agent_framework").setLevel(logging.WARNING)
P = Principal("lo-1", "contoso-mortgage", frozenset({"underwriting"}))


def test_every_agent_publishes_card_at_well_known_paths():
    for spec in CATALOG:
        c = TestClient(create_a2a_app(spec, HANDLERS[spec.id]))
        card = c.get("/.well-known/agent-card.json").json()
        assert card == c.get("/.well-known/agent.json").json()  # legacy alias
        assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
        ext = card["capabilities"]["extensions"][0]
        assert ext["uri"] == CONTROL_PLANE_EXT
        assert ext["params"]["owner"] and ext["params"]["allowed_callers"]
        assert ext["params"]["standin"] == spec.standin


def test_vendor_standins_are_clearly_labelled():
    standins = [s for s in CATALOG if s.standin]
    assert {s.vendor_style for s in standins} == {"Dynamics 365-style", "Salesforce-style", "SAP-style"}
    for s in standins:
        assert "STAND-IN" in s.name and "STAND-IN" in s.description and s.stage != "production"
        assert card_json(s)["capabilities"]["extensions"][0]["params"]["vendor_style"] == s.vendor_style


async def test_a2a_call_propagates_traceparent_and_tenant():
    tp = new_traceparent()
    out = await local_client("mortgage-underwriting").send(
        "crm-agent", "get_borrower_profile", {"borrower_id": "B-1001"}, P, tp
    )
    assert out["output"]["tenant"] == "contoso-mortgage"
    assert out["trace_id"] == trace_id_of(tp)


async def test_policy_denies_unlisted_caller_before_network():
    with pytest.raises(A2AError) as e:
        await local_client("experience-bff").send("erp-agent", "get_fee_ledger", {"loan_id": "L-1001"}, P)
    assert e.value.code == "forbidden"


async def test_server_enforces_policy_even_if_client_bypasses_it():
    app = local_apps()["erp-agent"]
    body = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "m",
                "role": "ROLE_USER",
                "parts": [{"data": {"skill": "get_fee_ledger", "input": {"loan_id": "L-1001"}}}],
            }
        },
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://erp") as c:
        r = await c.post(
            "/a2a",
            json=body,
            headers={
                "A2A-Version": "1.0",
                "traceparent": new_traceparent(),
                "x-tenant-id": "t",
                "x-caller-agent": "rogue-bot",
            },
        )
        data = r.json()["result"]["message"]["parts"][0]["data"]
        assert data["error"] == "forbidden"
        r = await c.post("/a2a", json=body, headers={"A2A-Version": "1.0"})
        assert r.json()["result"]["message"]["parts"][0]["data"]["error"] == "missing_headers"


async def test_kill_switch_blocks_agent():
    DIRECTORY.kill("crm-agent")
    with pytest.raises(A2AError) as e:
        await local_client("mortgage-underwriting").send(
            "crm-agent", "get_borrower_profile", {"borrower_id": "B-1001"}, P
        )
    assert "kill switch" in str(e.value.detail)
    DIRECTORY.revive("crm-agent")


async def test_write_hitl_skill_requires_approval_and_writes_are_idempotent():
    c = local_client("mortgage-underwriting")
    out = await c.send("sap-erp-standin", "commit_posting", {"loan_id": "L-1001", "idempotency_key": "k"}, P)
    assert out["status"] == "approval_required"
    a = await c.send(
        "sap-erp-standin",
        "commit_posting",
        {"loan_id": "L-1001", "idempotency_key": "k9", "approved_by": "ctl"},
        P,
    )
    b = await c.send(
        "sap-erp-standin",
        "commit_posting",
        {"loan_id": "L-1001", "idempotency_key": "k9", "approved_by": "ctl"},
        P,
    )
    assert a["output"] == b["output"]


async def test_bff_to_underwriting_agent_to_crm_agent_chain():
    tp = new_traceparent()
    out = await local_client("experience-bff").send(
        "underwriting-agent", "submit_loan_file", {"loan_id": "L-1001"}, P, tp
    )
    assert out["output"]["status"] == "awaiting_underwriter"
    assert out["trace_id"] == trace_id_of(tp)


def test_registration_promotion_gate():
    weak = AgentSpec(
        "new-agent",
        "New",
        "d",
        "team",
        "0.1.0",
        (SkillSpec("x", "x", "x"),),
        ("experience-bff",),
        eval_score=0.6,
    )
    assert not DIRECTORY.register(weak).allowed
    assert spec_by_id("crm-agent").side_effect_class == "write-queued"


def test_checked_in_cards_are_current():
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "scripts" / "export_agent_cards.py"
    spec = importlib.util.spec_from_file_location("export_cards", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(check=True) == 0
