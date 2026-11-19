"""Checkpoint, human wait, and resume on a new worker without re-billing finished model calls."""

import pytest

from agentplatform.ignite.durable import (
    AGENT_SPECS,
    DurableError,
    DurableWorkflowWorker,
    InquiryLog,
    ModelClient,
    TaskHub,
    billed_tokens,
    charges,
)


def _workers(hub: TaskHub | None = None, bureau: InquiryLog | None = None):
    hub = hub or TaskHub()
    bureau = bureau or InquiryLog()
    worker = DurableWorkflowWorker("worker-a", hub, ModelClient(), bureau)
    return hub, bureau, worker


def test_wait_releases_the_worker_before_any_letter():
    _hub, bureau, worker = _workers()
    state = worker.start("APP-4401")
    assert state["status"] == "waiting"
    assert worker.compute_held is False
    assert state["pending_request"]["proposed_decision"] == "approve_with_conditions"
    assert [item["agent"] for item in charges(state)] == ["intake", "credit"]
    assert all(item["worker_id"] == "worker-a" for item in charges(state))
    assert worker.model.invocations == ["intake", "credit"]
    assert bureau.attempts == 1
    assert bureau.hard_pulls == 1
    assert "book" not in {event["step"] for event in state["history"]}
    assert state["history"][0]["output"]["principal"] == "250000.00"
    assert "250000.00" not in state["history"][0]["output"]["narrative"]


def test_new_worker_does_not_rebill_finished_model_calls():
    hub, bureau, worker_a = _workers()
    waiting = worker_a.start("APP-4401")
    tokens_while_waiting = billed_tokens(waiting)
    assert tokens_while_waiting == 120 + 40 + 180 + 60

    worker_b = DurableWorkflowWorker("worker-b", TaskHub.loads(hub.export()), ModelClient(), bureau)
    finished = worker_b.signal("APP-4401", officer_id="officer-lee", approved=True, reason="ok")
    assert worker_b.compute_held is False
    assert worker_b.model.invocations == ["letter"]
    assert worker_a.model.invocations == ["intake", "credit"]
    assert [item["worker_id"] for item in charges(finished)] == ["worker-a", "worker-a", "worker-b"]
    assert [item["agent"] for item in charges(finished)] == ["intake", "credit", "letter"]
    assert billed_tokens(finished) == tokens_while_waiting + 200 + 80
    assert bureau.attempts == 1
    assert bureau.hard_pulls == 1
    booked = next(event for event in finished["history"] if event["step"] == "book")
    assert booked["kind"] == "activity"
    assert booked["charge"] is None
    assert booked["output"]["approved_by"] == "officer-lee"
    assert finished["history"][-2]["output"]["officer_id"] == "officer-lee"

    replayed = worker_b.signal("APP-4401", officer_id="officer-lee", approved=True)
    assert billed_tokens(replayed) == billed_tokens(finished)
    assert worker_b.model.invocations == ["letter"]


def test_crash_after_intake_resumes_credit_on_another_worker():
    hub, bureau, worker_a = _workers()
    parked = worker_a.start("APP-4401", stop_after="intake")
    assert parked["status"] == "running"
    assert worker_a.model.invocations == ["intake"]
    assert bureau.attempts == 0
    del worker_a

    worker_b = DurableWorkflowWorker("worker-b", TaskHub.loads(hub.export()), ModelClient(), bureau)
    waiting = worker_b.drive("APP-4401")
    assert waiting["status"] == "waiting"
    assert worker_b.model.invocations == ["credit"]
    assert [item["worker_id"] for item in charges(waiting)] == ["worker-a", "worker-b"]
    assert bureau.hard_pulls == 1

    done = worker_b.signal("APP-4401", officer_id="officer-lee", approved=True)
    assert worker_b.model.invocations == ["credit", "letter"]
    assert billed_tokens(done) == 120 + 40 + 180 + 60 + 200 + 80


def test_denial_skips_the_letter_model():
    _hub, bureau, worker = _workers()
    worker.start("APP-4401")
    denied = worker.signal(
        "APP-4401", officer_id="officer-lee", approved=False, reason="Policy exception refused."
    )
    assert denied["status"] == "completed"
    assert worker.model.invocations == ["intake", "credit"]
    steps = [event["step"] for event in denied["history"]]
    assert steps == ["intake", "credit", "credit_officer", "adverse_notice"]
    notice = denied["history"][-1]
    assert notice["kind"] == "activity"
    assert notice["charge"] is None
    assert notice["output"]["reason"] == "Policy exception refused."
    assert notice["output"]["booked"] is False
    assert bureau.attempts == 1
    assert billed_tokens(denied) == 400


def test_bureau_replay_would_not_be_a_second_hard_pull():
    log = InquiryLog()
    first = log.pull("bureau-APP-4401", 718)
    second = log.pull("bureau-APP-4401", 718)
    assert first == second
    assert log.attempts == 2
    assert log.hard_pulls == 1


def test_checkpoint_round_trip_is_plain_json():
    hub, _bureau, worker = _workers()
    worker.start("APP-4401")
    raw = hub.export()
    assert raw.startswith("{")
    restored = TaskHub.loads(raw)
    assert restored.get("APP-4401")["status"] == "waiting"
    assert restored.export() == raw


def test_unnamed_officer_and_unknown_agent_are_rejected():
    _hub, _bureau, worker = _workers()
    worker.start("APP-4401")
    with pytest.raises(DurableError, match="named credit officer"):
        worker.signal("APP-4401", officer_id=" ", approved=True)
    assert worker.model.invocations == ["intake", "credit"]
    with pytest.raises(DurableError, match="not registered"):
        worker.get_agent("collections")
    with pytest.raises(DurableError, match="unknown application"):
        worker.start("APP-missing")
    assert set(AGENT_SPECS) == {"intake", "credit", "letter"}
