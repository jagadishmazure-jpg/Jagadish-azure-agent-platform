"""Agent cards. One contract for first-party domain agents and vendor stand-ins.

Control-plane metadata (owner, side-effect class, allowed callers, tenants, eval score, prompt refs,
stand-in flag) is carried as an A2A `AgentExtension` because the 1.0 card has no free-form metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentInterface,
    AgentProvider,
    AgentSkill,
)
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct

CONTROL_PLANE_EXT = "urn:agentplatform:control-plane:v1"
A2A_PROTOCOL_VERSION = "1.0"


@dataclass(frozen=True)
class SkillSpec:
    id: str
    name: str
    description: str
    side_effect: str = "read"  # read | write-queued | write-hitl
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    description: str
    owner: str
    version: str
    skills: tuple[SkillSpec, ...]
    allowed_callers: tuple[str, ...]
    tenants: tuple[str, ...] = ("*",)
    eval_score: float = 0.0
    stage: str = "production"  # dev | staging | production
    standin: bool = False
    vendor_style: str | None = None
    system_of_record: str = ""
    model_deployment: str | None = None
    prompt_refs: tuple[str, ...] = ()
    port: int = 8100
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def side_effect_class(self) -> str:
        order = ["read", "write-queued", "write-hitl"]
        return max((s.side_effect for s in self.skills), key=order.index, default="read")

    def url(self) -> str:
        env = os.environ.get(f"A2A_{self.id.upper().replace('-', '_')}_URL")
        return (env or f"http://{self.id}.local").rstrip("/") + "/a2a"

    def skill(self, skill_id: str) -> SkillSpec | None:
        return next((s for s in self.skills if s.id == skill_id), None)


def to_agent_card(spec: AgentSpec) -> AgentCard:
    params = Struct()
    params.update(
        {
            "agent_id": spec.id,
            "owner": spec.owner,
            "side_effect_class": spec.side_effect_class,
            "allowed_callers": list(spec.allowed_callers),
            "tenants": list(spec.tenants),
            "eval_score": spec.eval_score,
            "stage": spec.stage,
            "standin": spec.standin,
            "vendor_style": spec.vendor_style or "",
            "system_of_record": spec.system_of_record,
            "model_deployment": spec.model_deployment or "",
            "prompt_refs": list(spec.prompt_refs),
            "skill_side_effects": {s.id: s.side_effect for s in spec.skills},
            "requires_headers": ["traceparent", "x-tenant-id", "x-caller-agent"],
        }
    )
    return AgentCard(
        name=spec.name,
        description=spec.description,
        version=spec.version,
        provider=AgentProvider(
            organization="Contoso Mortgage (demo)", url="https://github.com/jagadishmazure-jpg"
        ),
        supported_interfaces=[
            AgentInterface(url=spec.url(), protocol_binding="JSONRPC", protocol_version=A2A_PROTOCOL_VERSION)
        ],
        capabilities=AgentCapabilities(
            streaming=False,
            extensions=[
                AgentExtension(
                    uri=CONTROL_PLANE_EXT,
                    description="Control-plane registration: owner, policy, side effects, eval gate",
                    required=False,
                    params=params,
                )
            ],
        ),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id=s.id,
                name=s.name,
                description=f"{s.description} [side-effect: {s.side_effect}]",
                tags=list(s.tags),
                examples=list(s.examples),
                input_modes=["application/json"],
                output_modes=["application/json"],
            )
            for s in spec.skills
        ],
    )


def card_json(spec: AgentSpec) -> dict:
    return MessageToDict(to_agent_card(spec))
