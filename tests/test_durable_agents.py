"""Offline Durable Task replay: completed model calls are not run again after resume."""

import pytest

from agentplatform.durable_agents.loan import build_loan_app, make_publisher
from agentplatform.durable_agents.runtime import (
    CrashBeforeCheckpoint,
    DurableAgentApp,
    JsonHistoryStore,
    NondeterministicOrchestration,
    OrchestrationContext,
)


def _app(tmp_path) -> tuple[DurableAgentApp, JsonHistoryStore]:
    store = JsonHistoryStore(tmp_path)
    return build_loan_app(store), store


def test_workflow_waits_without_calling_the_letter_agent(tmp_path):
    app, store = _app(tmp_path)
    state = app.start("loan_review", "run-1", {"loan_id": "L-2001"})
    assert state["status"] == "waiting"
    assert state["execution_log"] == ["intake", "credit"]
    assert app.agents["letter"].calls == []
    assert store.load("run-1")["execution_log"] == ["intake", "credit"]


def test_completed_model_calls_are_not_reexecuted_after_resume(tmp_path):
    app, store = _app(tmp_path)
    waiting = app.start("loan_review", "run-1", {"loan_id": "L-2001"})
    assert waiting["status"] == "waiting"
    first_intake = list(app.agents["intake"].calls)
    first_credit = list(app.agents["credit"].calls)
    assert first_intake == ["L-2001"]
    assert first_credit == ["L-2001"]

    restarted, _ = _app(tmp_path)
    assert restarted.agents["intake"].calls == []
    assert restarted.agents["credit"].calls == []
    still = restarted.resume("loan_review", "run-1")
    assert still["status"] == "waiting"
    assert restarted.agents["intake"].calls == []
    assert restarted.agents["credit"].calls == []
    assert store.load("run-1")["execution_log"] == ["intake", "credit"]

    restarted.raise_event("run-1", "underwriter_approval", {"approved": True, "approver": "uw-1"})
    done = restarted.resume("loan_review", "run-1")
    saved = store.load("run-1")
    assert done["status"] == "completed"
    assert done["output"]["status"] == "issued"
    assert done["output"]["approver"] == "uw-1"
    assert done["output"]["ticket"] == "LET-L-2001"
    assert done["output"]["duplicate"] is False
    assert "DTI 41 percent" in done["output"]["letter"]
    assert restarted.agents["intake"].calls == []
    assert restarted.agents["credit"].calls == []
    assert len(restarted.agents["letter"].calls) == 1
    assert saved["execution_log"] == ["intake", "credit", "letter", "publish_letter"]
    assert saved["attempts"].count("intake") == 1
    assert saved["attempts"].count("credit") == 1
    assert saved["attempts"].count("letter") == 1

    third, _ = _app(tmp_path)
    again = third.resume("loan_review", "run-1")
    assert again["output"] == done["output"]
    assert third.agents["intake"].calls == []
    assert third.agents["credit"].calls == []
    assert third.agents["letter"].calls == []
    assert store.load("run-1")["execution_log"] == ["intake", "credit", "letter", "publish_letter"]
    assert store.load("run-1")["attempts"] == saved["attempts"]


def test_denial_skips_the_letter_and_the_publish(tmp_path):
    app, store = _app(tmp_path)
    app.start("loan_review", "run-2", {"loan_id": "L-2002"})
    app.raise_event("run-2", "underwriter_approval", {"approved": False, "approver": "uw-9"})
    done = app.resume("loan_review", "run-2")
    assert done["output"]["status"] == "returned_to_processing"
    assert done["execution_log"] == ["intake", "credit"]
    assert app.agents["letter"].calls == []

    app.raise_event("run-2", "underwriter_approval", {"approved": True, "approver": ""})
    # The run has already completed, so a late event is not a second letter.
    replayed = app.resume("loan_review", "run-2")
    assert replayed["output"]["status"] == "returned_to_processing"
    assert app.agents["letter"].calls == []
    assert store.load("run-2")["execution_log"] == ["intake", "credit"]


def test_missing_approver_returns_the_file(tmp_path):
    app, _store = _app(tmp_path)
    app.start("loan_review", "run-3", {"loan_id": "L-2001"})
    app.raise_event("run-3", "underwriter_approval", {"approved": True, "approver": ""})
    done = app.resume("loan_review", "run-3")
    assert done["output"]["status"] == "returned_to_processing"
    assert app.agents["letter"].calls == []


def test_uncheckpointed_model_call_is_retried(tmp_path):
    app, store = _app(tmp_path)
    app.start("loan_review", "run-4", {"loan_id": "L-2001"})
    app.raise_event("run-4", "underwriter_approval", {"approved": True, "approver": "uw-1"})
    app.crash_before_checkpoint.add("letter")
    with pytest.raises(CrashBeforeCheckpoint):
        app.resume("loan_review", "run-4")
    assert len(app.agents["letter"].calls) == 1
    interrupted = store.load("run-4")
    assert interrupted["status"] == "interrupted"
    assert "letter" in interrupted["attempts"]
    assert "letter" not in interrupted["execution_log"]
    assert interrupted["execution_log"] == ["intake", "credit"]

    restarted, _ = _app(tmp_path)
    done = restarted.resume("loan_review", "run-4")
    saved = store.load("run-4")
    assert done["output"]["status"] == "issued"
    assert len(restarted.agents["letter"].calls) == 1
    assert restarted.agents["intake"].calls == []
    assert restarted.agents["credit"].calls == []
    assert saved["attempts"].count("letter") == 2
    assert saved["attempts"].count("intake") == 1
    assert saved["execution_log"].count("letter") == 1
    assert saved["execution_log"].count("publish_letter") == 1


def test_changed_orchestration_is_nondeterministic(tmp_path):
    app, _store = _app(tmp_path)
    app.start("loan_review", "run-5", {"loan_id": "L-2001"})

    def swapped(ctx: OrchestrationContext):
        loan_id = ctx.get_input()["loan_id"]
        yield ctx.call_agent("credit", loan_id)
        yield ctx.call_agent("intake", loan_id)

    restarted, _ = _app(tmp_path)
    restarted.orchestrations["loan_review"] = swapped
    with pytest.raises(NondeterministicOrchestration, match="credit"):
        restarted.resume("loan_review", "run-5")


def test_publish_activity_is_idempotent():
    ledger: dict = {}
    publish = make_publisher(ledger)
    payload = {"loan_id": "L-2001", "idempotency_key": "L-2001:letter", "text": "letter"}
    first = publish(payload)
    second = publish(payload)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["ticket"] == first["ticket"] == "LET-L-2001"
