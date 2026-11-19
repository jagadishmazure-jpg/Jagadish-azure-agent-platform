"""Offline stand-in for a hosted agent on the Microsoft Copilot harness.

Microsoft runs the loop and the sandbox. The caller supplies the agent definition:
instructions, knowledge, skills, and tools reached through the Toolbox MCP endpoint.
See ``assumptions.py`` before treating a behavior as a product guarantee.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from mcp import Client

from agentplatform.ignite.assumptions import MATURITY
from agentplatform.ignite.data import KnowledgeItem
from agentplatform.ignite.toolbox import TOOL_POLICIES, LoanToolbox


class HarnessError(RuntimeError):
    pass


class TakeControl(HarnessError):
    """Browser automation asked a person to take the session (Live View / Take control)."""

    def __init__(self, payload: dict) -> None:
        super().__init__("browser session is waiting for a person to take control")
        self.payload = payload


class SkillContext(Protocol):
    application_id: str
    knowledge: dict[str, KnowledgeItem]
    state: dict[str, Any]
    approval: CreditDecision | None

    async def call_tool(self, name: str, args: dict) -> dict:
        """Call one tool on the Toolbox MCP endpoint."""
        raise NotImplementedError


@dataclass
class CreditDecision:
    officer_id: str
    approved: bool
    reason: str = ""


class Skill:
    """A reusable skill the bank supplies. The harness does not author skills."""

    name: str
    requires_approval: bool = False

    async def run(self, ctx: SkillContext) -> None:
        raise NotImplementedError(self.name)


@dataclass
class AgentDefinition:
    """Source-controlled agent definition. The harness does not author this."""

    name: str
    instructions: str
    knowledge: tuple[KnowledgeItem, ...]
    skills: tuple[Skill, ...]
    toolbox_name: str
    voice_enabled: bool = False

    def skill_names(self) -> tuple[str, ...]:
        return tuple(skill.name for skill in self.skills)


def attach_voice(definition: AgentDefinition) -> AgentDefinition:
    """Voice is GA and is added to an existing agent without replacing its skills or tools."""
    return AgentDefinition(
        name=definition.name,
        instructions=definition.instructions,
        knowledge=definition.knowledge,
        skills=definition.skills,
        toolbox_name=definition.toolbox_name,
        voice_enabled=True,
    )


@dataclass
class Sandbox:
    """The platform sandbox. Egress is refused outside the agent code.

    The post documents egress controls for hosted agents (GA), enforced outside the sandbox.
    Applying that block to this harness demo is an assumption; see ASSUMPTIONS.
    """

    network_allowed: bool = False
    blocked_hosts: list[str] = field(default_factory=list)

    def enforce_egress(self, host: str) -> None:
        if self.network_allowed:
            return
        self.blocked_hosts.append(host)
        raise HarnessError(f"egress to {host} blocked outside the sandbox")


@dataclass
class HarnessRun:
    run_id: str
    application_id: str
    status: str
    compute_held: bool
    completed_skills: list[str]
    state: dict[str, Any]
    approval: CreditDecision | None = None
    instructions: str = ""

    def to_record(self) -> dict[str, Any]:
        approval = None
        if self.approval is not None:
            approval = {
                "officer_id": self.approval.officer_id,
                "approved": self.approval.approved,
                "reason": self.approval.reason,
            }
        return {
            "run_id": self.run_id,
            "application_id": self.application_id,
            "status": self.status,
            "compute_held": self.compute_held,
            "completed_skills": list(self.completed_skills),
            "state": self.state,
            "approval": approval,
            "instructions": self.instructions,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> HarnessRun:
        raw = record["approval"]
        approval = None if raw is None else CreditDecision(**raw)
        return cls(
            run_id=record["run_id"],
            application_id=record["application_id"],
            status=record["status"],
            compute_held=record["compute_held"],
            completed_skills=list(record["completed_skills"]),
            state=record["state"],
            approval=approval,
            instructions=record["instructions"],
        )


class SessionStore:
    """Saved session state. Idle hosted agents release compute and keep this state."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}

    def save(self, run: HarnessRun) -> None:
        self._runs[run.run_id] = json.loads(json.dumps(run.to_record()))

    def load(self, run_id: str) -> HarnessRun:
        try:
            record = self._runs[run_id]
        except KeyError as exc:
            raise HarnessError(f"unknown run {run_id}") from exc
        return HarnessRun.from_record(record)


class ToolboxClient:
    """The only path from the harness to tools: the Toolbox MCP endpoint, then policy."""

    def __init__(self, toolbox: LoanToolbox) -> None:
        self.toolbox = toolbox
        self._names: list[str] | None = None

    async def list_tools(self) -> list[str]:
        if self._names is None:
            async with Client(self.toolbox.server) as client:
                listed = await client.list_tools()
            self._names = sorted(tool.name for tool in listed.tools)
        return list(self._names)

    async def call(self, name: str, args: dict) -> dict:
        if name not in await self.list_tools():
            raise HarnessError(f"tool {name} is not on the toolbox")
        policy = TOOL_POLICIES[name]
        if policy.get("requires_approval") and not str(args.get("approved_by", "")).strip():
            self.toolbox.metrics["blocked_by_policy"] += 1
            raise HarnessError(f"tool policy blocked {name}")
        payload = await self._invoke(name, args)
        if payload.get("take_control_required"):
            raise TakeControl(payload)
        return payload

    async def _invoke(self, name: str, args: dict) -> dict:
        async with Client(self.toolbox.server) as client:
            result = await client.call_tool(name, args)
        if result.is_error:
            text = " ".join(getattr(block, "text", "") for block in result.content)
            raise HarnessError(text or name)
        payload = result.structured_content
        if payload is None:
            payload = json.loads(result.content[0].text)
        if not isinstance(payload, dict):
            raise HarnessError(f"{name} returned a non-object")
        return payload


@dataclass
class _BoundContext:
    application_id: str
    knowledge: dict[str, KnowledgeItem]
    state: dict[str, Any]
    approval: CreditDecision | None
    tools: ToolboxClient

    async def call_tool(self, name: str, args: dict) -> dict:
        return await self.tools.call(name, args)


class CopilotHarness:
    """Platform loop. ``handler_runs`` counts entries, including crash recovery.

    Recovery of a hosted agent reruns the handler (GA). Skills already saved on the
    session are not run again, which is how this demo avoids a second bureau pull or booking.
    """

    def __init__(self, toolbox: LoanToolbox, definition: AgentDefinition) -> None:
        self.toolbox = toolbox
        self.definition = definition
        self.tools = ToolboxClient(toolbox)
        self.sessions = SessionStore()
        self.sandbox = Sandbox()
        self.handler_runs = 0

    def _require_definition(self) -> None:
        if not self.definition.instructions.strip():
            raise HarnessError("the agent definition has no instructions")
        if not self.definition.knowledge:
            raise HarnessError("the platform does not supply knowledge")
        if not self.definition.skills:
            raise HarnessError("the platform does not supply skills")
        if self.definition.toolbox_name != self.toolbox.name:
            raise HarnessError("the agent is not bound to this toolbox")

    async def start(self, application_id: str) -> HarnessRun:
        self._require_definition()
        run = HarnessRun(
            run_id=f"harness-{application_id}",
            application_id=application_id,
            status="running",
            compute_held=True,
            completed_skills=[],
            state={},
            instructions=self.definition.instructions,
        )
        self.sessions.save(run)
        return await self._enter(run.run_id, approval=None)

    async def resume(self, run_id: str, *, officer_id: str, approved: bool, reason: str = "") -> HarnessRun:
        if not officer_id.strip():
            raise HarnessError("a named credit officer is required")
        return await self._enter(run_id, CreditDecision(officer_id.strip(), approved, reason))

    async def recover(self, run_id: str) -> HarnessRun:
        """Rerun the handler from saved progress. This is the hosted-agent recovery rule."""
        return await self._enter(run_id, approval=None)

    async def voice_turn(self, utterance: str, *, interrupt: bool = False) -> dict[str, Any]:
        """GA voice on the same definition. A spoken turn cannot book the loan."""
        voiced = attach_voice(self.definition)
        if voiced.skills is not self.definition.skills:
            raise HarnessError("voice replaced the agent's skills")
        bookings = self.toolbox.metrics["bookings"]
        reply = ""
        if not interrupt and utterance.strip():
            reply = "A named credit officer has to approve before this loan can be booked."
        return {
            "voice_enabled": True,
            "maturity": MATURITY["voice"],
            "telephony": "native",
            "barged_in": interrupt,
            "reply": reply,
            "skills": voiced.skill_names(),
            "bookings": bookings,
        }

    async def request_browser_take_control(self, purpose: str) -> HarnessRun:
        """Open an isolated browser session and pause when Take control is required."""
        self.handler_runs += 1
        slug = "-".join(purpose.lower().split())
        run = HarnessRun(
            run_id=f"browser-{slug}",
            application_id=slug,
            status="running",
            compute_held=True,
            completed_skills=[],
            state={},
            instructions=self.definition.instructions,
        )
        try:
            session = await self.tools.call("open_browser_session", {"purpose": purpose})
            await self.tools.call(
                "browser_action", {"session_id": session["session_id"], "action": "take_control"}
            )
        except TakeControl as exc:
            run.status = "awaiting_browser_oversight"
            run.compute_held = False
            run.state = {
                "browser": exc.payload,
                "recording_uri": session["recording_uri"],
                "isolated": session["isolated"],
                "fetched_url": session["fetched_url"],
            }
            self.sessions.save(run)
            return run
        raise HarnessError("take control was not requested")

    async def _enter(self, run_id: str, approval: CreditDecision | None) -> HarnessRun:
        self._require_definition()
        self.handler_runs += 1
        run = self.sessions.load(run_id)
        if approval is not None:
            run.approval = approval
        elif run.approval is not None:
            approval = run.approval
        run.compute_held = True
        ctx = _BoundContext(
            application_id=run.application_id,
            knowledge={item.id: item for item in self.definition.knowledge},
            state=run.state,
            approval=approval,
            tools=self.tools,
        )
        try:
            for skill in self.definition.skills:
                if skill.name in run.completed_skills:
                    continue
                if skill.requires_approval and run.approval is None:
                    run.status = "awaiting_credit_officer"
                    run.compute_held = False
                    self.sessions.save(run)
                    return run
                ctx.approval = run.approval
                await skill.run(ctx)
                run.completed_skills.append(skill.name)
                self.sessions.save(run)
        except TakeControl as exc:
            run.status = "awaiting_browser_oversight"
            run.compute_held = False
            run.state["browser"] = exc.payload
            self.sessions.save(run)
            return run
        run.status = "completed"
        run.compute_held = False
        self.sessions.save(run)
        return run
