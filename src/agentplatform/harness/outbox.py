"""Queued writes. The agent never writes a system of record synchronously: it enqueues a command with
an idempotency key; a worker (KEDA-scaled on queue depth) applies it. Azure: Service Bus (managed
identity). Offline: in-memory queue with a chaos hook."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentplatform.config import Settings, azure_credential, get_settings


class OutboxError(RuntimeError):
    pass


class Outbox(Protocol):
    def send(self, queue: str, payload: dict[str, Any], idempotency_key: str) -> str:
        """Enqueue ``payload`` once per ``idempotency_key`` and return the message id."""


@dataclass
class InMemoryOutbox:
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail_next: int = 0

    def send(self, queue: str, payload: dict[str, Any], idempotency_key: str) -> str:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise OutboxError("service bus unavailable (simulated)")
        self.messages.setdefault(idempotency_key, {"queue": queue, "payload": payload})
        return idempotency_key

    def void(self, idempotency_key: str) -> None:
        self.messages.pop(idempotency_key, None)


class ServiceBusOutbox:
    """Service Bus sender; `message_id` = idempotency key so duplicate detection drops replays
    (enable requiresDuplicateDetection on Standard tier; Basic tier relies on consumer idempotency)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def send(self, queue: str, payload: dict[str, Any], idempotency_key: str) -> str:
        from azure.servicebus import ServiceBusClient, ServiceBusMessage

        with (
            ServiceBusClient(self.settings.servicebus_namespace, azure_credential(self.settings)) as client,
            client.get_queue_sender(queue) as sender,
        ):
            sender.send_messages(ServiceBusMessage(json.dumps(payload), message_id=idempotency_key))
        return idempotency_key

    def void(self, idempotency_key: str) -> None:  # compensation is a new command, not a delete
        self.send("compensations", {"void": idempotency_key}, f"void:{idempotency_key}")


def get_outbox(settings: Settings | None = None):
    s = settings or get_settings()
    return ServiceBusOutbox(s) if (s.azure and s.servicebus_namespace) else InMemoryOutbox()
