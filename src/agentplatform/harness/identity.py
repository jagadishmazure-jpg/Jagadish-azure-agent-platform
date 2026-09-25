"""Caller identity + tenant envelope propagated through every node, tool, and A2A hop."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """Who is acting. `agent_id` is the workload identity (a user-assigned MI in Azure)."""

    subject: str
    tenant_id: str
    groups: frozenset[str] = field(default_factory=frozenset)
    agent_id: str | None = None
    on_behalf_of: str | None = None

    def with_agent(self, agent_id: str) -> Principal:
        return Principal(self.subject, self.tenant_id, self.groups, agent_id, self.on_behalf_of)


def new_traceparent(trace_id: str | None = None) -> str:
    """W3C trace-context header: version-traceid-parentid-flags."""
    trace_id = trace_id or secrets.token_hex(16)
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


def child_traceparent(traceparent: str | None) -> str:
    """Same trace id, new span id — how A2A hops stitch together in App Insights."""
    if not traceparent or traceparent.count("-") != 3:
        return new_traceparent()
    _, trace_id, _, flags = traceparent.split("-")
    return f"00-{trace_id}-{secrets.token_hex(8)}-{flags}"


def trace_id_of(traceparent: str) -> str:
    return traceparent.split("-")[1] if traceparent and traceparent.count("-") == 3 else ""
