"""Replay runtime for durable multi-agent workflows.

[verify] Microsoft Learn shows ``AgentFunctionApp``, ``app.get_agent``,
``DurableAIAgentWorker`` and ``durabletask.azuremanaged.worker.DurableTaskSchedulerWorker``.
Those packages are not pinned here and were not executed. This runtime copies the
documented rule: on resume, a completed agent call is read from history and the model
is not called again. A call that did not reach its checkpoint is run again.

Human approval is an external event. The orchestration stays parked, with no compute
and no further model calls, until that event is raised.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

_INSTANCE = re.compile(r"[A-Za-z0-9_-]+")
_KIND = {"agent": "agent_completed", "activity": "activity_completed", "event": "event_raised"}


class NondeterministicOrchestration(RuntimeError):
    """The replayed code requested a different step than the checkpoint records."""


class CrashBeforeCheckpoint(RuntimeError):
    """The step ran, then the process stopped before the completion was saved."""


class DurableAgent:
    """Stand-in for a durable agent. ``run`` is the model call the tests count."""

    def __init__(self, name: str, respond: Callable[[str], dict[str, Any]]) -> None:
        self.name = name
        self.respond = respond
        self.calls: list[str] = []

    def run(self, message: str) -> dict[str, Any]:
        self.calls.append(message)
        return self.respond(message)


class OrchestrationContext:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def get_input(self) -> dict[str, Any]:
        return self._payload

    def call_agent(self, name: str, message: str) -> tuple[str, str, Any]:
        """[verify] Stand-in for ``yield agent.run(messages=..., session=...)``."""
        return ("agent", name, message)

    def call_activity(self, name: str, payload: dict[str, Any]) -> tuple[str, str, Any]:
        return ("activity", name, payload)

    def wait_for_event(self, name: str) -> tuple[str, str, Any]:
        """Durable human-approval wait. No model call while this is pending."""
        return ("event", name, None)


class JsonHistoryStore:
    """One JSON file per instance, so a new process can resume after a crash."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def exists(self, instance_id: str) -> bool:
        return self._path(instance_id).exists()

    def create(self, instance_id: str, orchestration: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "instance_id": instance_id,
            "orchestration": orchestration,
            "input": payload,
            "status": "running",
            "events": [],
            "inbox": {},
            "output": None,
            "execution_log": [],
            "attempts": [],
        }
        self.save(record)
        return record

    def load(self, instance_id: str) -> dict[str, Any]:
        return json.loads(self._path(instance_id).read_text())

    def save(self, record: dict[str, Any]) -> None:
        path = self._path(record["instance_id"])
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    def _path(self, instance_id: str) -> Path:
        if not _INSTANCE.fullmatch(instance_id):
            raise ValueError("instance id must be a simple token")
        return self.directory / f"{instance_id}.json"


class DurableAgentApp:
    """Offline stand-in for ``AgentFunctionApp`` / ``DurableAIAgentWorker``. [verify]"""

    def __init__(self, store: JsonHistoryStore) -> None:
        self.store = store
        self.agents: dict[str, DurableAgent] = {}
        self.activities: dict[str, Callable[..., dict[str, Any]]] = {}
        self.orchestrations: dict[str, Callable[..., Any]] = {}
        self.crash_before_checkpoint: set[str] = set()

    def add_agent(self, agent: DurableAgent) -> None:
        self.agents[agent.name] = agent

    def add_activity(self, name: str, fn: Callable[..., dict[str, Any]]) -> None:
        self.activities[name] = fn

    def start(self, name: str, instance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in self.orchestrations:
            raise KeyError(name)
        if self.store.exists(instance_id):
            raise RuntimeError(f"instance {instance_id} already exists")
        record = self.store.create(instance_id, name, payload)
        return self.drive(name, record)

    def raise_event(self, instance_id: str, name: str, payload: dict[str, Any]) -> None:
        record = self.store.load(instance_id)
        record["inbox"].setdefault(name, []).append(payload)
        self.store.save(record)

    def resume(self, name: str, instance_id: str) -> dict[str, Any]:
        record = self.store.load(instance_id)
        if record["orchestration"] != name:
            raise RuntimeError("orchestration name does not match the checkpoint")
        return self.drive(name, record)

    def drive(self, name: str, record: dict[str, Any]) -> dict[str, Any]:
        """Replay completed steps, then execute only the step that has no checkpoint."""
        context = OrchestrationContext(record["input"])
        generator = self.orchestrations[name](context)
        pending: Any = None
        position = 0
        while True:
            try:
                kind, step_name, payload = generator.send(pending)
            except StopIteration as stop:
                record["output"] = stop.value
                record["status"] = "completed"
                self.store.save(record)
                return record
            if position < len(record["events"]):
                event = record["events"][position]
                self._require_match(event, kind, step_name, payload)
                pending = event["result"]
                position += 1
                continue
            if kind == "event":
                inbox = record["inbox"].get(step_name) or []
                if not inbox:
                    record["status"] = "waiting"
                    self.store.save(record)
                    return record
                result = inbox.pop(0)
                record["events"].append(
                    {"kind": "event_raised", "name": step_name, "payload": None, "result": result}
                )
                self.store.save(record)
                pending = result
                position += 1
                continue
            pending = self._execute(record, kind, step_name, payload)
            position += 1

    def _execute(self, record: dict[str, Any], kind: str, name: str, payload: Any) -> Any:
        if kind == "agent":
            result = self.agents[name].run(payload)
        elif kind == "activity":
            result = self.activities[name](payload)
        else:
            raise RuntimeError(f"unsupported step {kind}")
        record["attempts"].append(name)
        self.store.save(record)
        if name in self.crash_before_checkpoint:
            self.crash_before_checkpoint.remove(name)
            record["status"] = "interrupted"
            self.store.save(record)
            raise CrashBeforeCheckpoint(name)
        record["events"].append({"kind": _KIND[kind], "name": name, "payload": payload, "result": result})
        record["execution_log"].append(name)
        record["status"] = "running"
        self.store.save(record)
        return result

    def _require_match(self, event: dict[str, Any], kind: str, name: str, payload: Any) -> None:
        expected = _KIND[kind]
        payload_ok = kind == "event" or event.get("payload") == payload
        if event.get("kind") != expected or event.get("name") != name or not payload_ok:
            raise NondeterministicOrchestration(
                f"history has {event.get('kind')} {event.get('name')!r} but the orchestration "
                f"requested {expected} {name!r}"
            )
