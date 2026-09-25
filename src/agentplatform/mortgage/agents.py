"""Agent layer: one MAF `Agent` per role, instructions from the versioned prompt pack, structured
output bound to the prompt's schema. Numbers/citations are computed by tools; the agent polishes
language. Model failure -> fallback deployment -> deterministic draft (degrade exit)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Agent, BaseChatClient

from agentplatform.harness.tracing import span
from agentplatform.llm.clients import get_chat_client
from agentplatform.prompts import load_pack

ROLES = {
    "intake": "mortgage.intake",
    "income": "mortgage.income",
    "assets": "mortgage.assets",
    "credit": "mortgage.credit",
    "conditions": "mortgage.conditions",
    "critic": "mortgage.critic",
    "letter": "mortgage.decision_letter",
}


@dataclass
class AgentSuite:
    client: BaseChatClient | None = None
    fallback: BaseChatClient | None = None
    agents: dict[str, Agent] = field(default_factory=dict)
    prompt_refs: dict[str, str] = field(default_factory=dict)
    degraded: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        pack = load_pack()
        self.client = self.client or get_chat_client()
        for role, pid in ROLES.items():
            spec = pack.get(pid)
            self.prompt_refs[role] = spec.ref
            self.agents[role] = Agent(
                client=self.client,
                name=f"{role}-agent",
                instructions=spec.body,
                description=f"mortgage {role} agent ({spec.ref})",
            )

    async def structured(
        self, role: str, *, facts: dict[str, Any], draft: dict[str, Any], evidence: str = ""
    ) -> dict:
        spec = load_pack().get(ROLES[role])
        schema = spec.schema()
        message = (
            f"{evidence}\n\nUse only the facts and evidence above. Return JSON for schema {spec.output_schema}.\n"
            f"```json\n{json.dumps({'facts': facts, 'draft': draft}, default=str)}\n```"
        )
        with span("agent.run", agent=f"{role}-agent", prompt=spec.ref):
            for client in (None, self.fallback):
                try:
                    agent = (
                        self.agents[role] if client is None else Agent(client=client, instructions=spec.body)
                    )
                    resp = await agent.run(message, options={"response_format": schema})
                    if resp.value is not None:
                        return resp.value.model_dump()
                except Exception:  # model endpoint failure -> next option
                    continue
        self.degraded.append(role)
        return schema.model_validate(draft).model_dump()  # degrade: deterministic draft, still schema-valid
