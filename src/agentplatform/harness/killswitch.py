"""Kill switch: global, per-agent, and per-tenant. APIM enforces the same flag at the edge
(infra/modules/apim.bicep policy returns 503 when the named value `killswitch-<agent>` is true);
this in-process switch makes the graph stop between nodes even for in-flight runs."""

from __future__ import annotations

import threading


class AgentDisabled(RuntimeError):
    pass


class KillSwitch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global = False
        self._agents: set[str] = set()
        self._tenants: set[str] = set()

    def trip(self, *, agent: str | None = None, tenant: str | None = None, everything: bool = False) -> None:
        with self._lock:
            if everything:
                self._global = True
            if agent:
                self._agents.add(agent)
            if tenant:
                self._tenants.add(tenant)

    def reset(self, *, agent: str | None = None, tenant: str | None = None, everything: bool = False) -> None:
        with self._lock:
            if everything:
                self._global = False
                self._agents.clear()
                self._tenants.clear()
            if agent:
                self._agents.discard(agent)
            if tenant:
                self._tenants.discard(tenant)

    def is_tripped(self, agent: str | None = None, tenant: str | None = None) -> bool:
        return self._global or (agent in self._agents) or (tenant in self._tenants)

    def check(self, agent: str | None = None, tenant: str | None = None) -> None:
        if self.is_tripped(agent, tenant):
            raise AgentDisabled(f"kill switch engaged (agent={agent}, tenant={tenant})")

    def state(self) -> dict:
        return {"global": self._global, "agents": sorted(self._agents), "tenants": sorted(self._tenants)}


KILL_SWITCH = KillSwitch()
