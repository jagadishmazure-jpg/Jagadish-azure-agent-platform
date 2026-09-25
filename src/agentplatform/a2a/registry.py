"""Control plane: directory + who-may-call-whom policy + promotion gate + kill switch.

Azure shape: cards stored next to Foundry eval reports; APIM enforces the same allow-list with
`validate-jwt` + a caller-claim check and a named-value kill switch (infra/modules/apim.bicep)."""

from __future__ import annotations

from dataclasses import dataclass

from agentplatform.a2a.cards import AgentSpec, card_json
from agentplatform.a2a.catalog import CATALOG
from agentplatform.harness.killswitch import KILL_SWITCH, KillSwitch

PROMOTION_MIN_EVAL = 0.85


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class AgentDirectory:
    def __init__(self, specs: tuple[AgentSpec, ...] = CATALOG, kill_switch: KillSwitch = KILL_SWITCH) -> None:
        self._specs = {s.id: s for s in specs}
        self.kill_switch = kill_switch

    def get(self, agent_id: str) -> AgentSpec:
        return self._specs[agent_id]

    def list(self) -> list[AgentSpec]:
        return list(self._specs.values())

    def register(self, spec: AgentSpec) -> PolicyDecision:
        """Registration before production DNS: production stage requires an eval score >= gate."""
        if spec.stage == "production" and spec.eval_score < PROMOTION_MIN_EVAL:
            return PolicyDecision(
                False, f"eval {spec.eval_score:.2f} below promotion gate {PROMOTION_MIN_EVAL}"
            )
        self._specs[spec.id] = spec
        return PolicyDecision(True, "registered")

    def authorize(self, caller: str, callee: str, tenant: str, skill: str) -> PolicyDecision:
        spec = self._specs.get(callee)
        if spec is None:
            return PolicyDecision(False, f"unknown agent {callee}")
        if self.kill_switch.is_tripped(callee, tenant):
            return PolicyDecision(False, f"kill switch engaged for {callee}/{tenant}")
        if caller not in spec.allowed_callers:
            return PolicyDecision(False, f"{caller} may not call {callee}")
        if "*" not in spec.tenants and tenant not in spec.tenants:
            return PolicyDecision(False, f"tenant {tenant} not enabled for {callee}")
        if spec.skill(skill) is None:
            return PolicyDecision(False, f"{callee} has no skill {skill}")
        return PolicyDecision(True, "allowed")

    def kill(self, agent_id: str) -> None:
        self.kill_switch.trip(agent=agent_id)

    def revive(self, agent_id: str) -> None:
        self.kill_switch.reset(agent=agent_id)

    def cards(self) -> list[dict]:
        return [card_json(s) for s in self._specs.values()]


DIRECTORY = AgentDirectory()
