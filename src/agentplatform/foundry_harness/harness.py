"""Offline Microsoft Copilot harness.

Microsoft runs the agent loop and the sandbox in Foundry Agent Service. This mock does
that job locally: it loads the skill and the in-force knowledge, offers only the tools
the Toolbox listed, refuses built-ins the sandbox has disabled, and holds any tool
whose ``require_approval`` is ``always`` until a named person approves.

[verify] ``harness.type: microsoft_copilot_preview`` is public preview. The real service
must be selected when the prompt agent is created. This class does not call Foundry.
"""

from __future__ import annotations

from datetime import date

from agentplatform.foundry_harness.models import (
    HarnessRun,
    KnowledgePassage,
    ModelAction,
    Sandbox,
    Skill,
)
from agentplatform.foundry_harness.toolbox import MockToolboxService

# [verify] public preview value from the Foundry Copilot harness authoring sample.
HARNESS_TYPE = "microsoft_copilot_preview"

_BUILTIN_SANDBOX = {
    "shell": "allow_shell",
    "web_fetch": "allow_web_fetch",
    "files": "allow_files",
    "subagent": "allow_subagents",
}


class ScriptedModel:
    """Deterministic stand-in for the Foundry model the harness calls.

    The script proposes actions. It cannot bypass the sandbox or an approval gate.
    """

    def __init__(self, actions: list[ModelAction]) -> None:
        self.actions = list(actions)
        self.calls = 0
        self.contexts: list[str] = []

    def complete(self, context: str) -> ModelAction:
        self.calls += 1
        self.contexts.append(context)
        if self.calls > len(self.actions):
            raise RuntimeError("scripted model has no further action")
        return self.actions[self.calls - 1]


def select_in_force(passages: list[KnowledgePassage], as_of: date) -> list[KnowledgePassage]:
    """Keep passages whose effective window contains ``as_of``. The model never sees the rest."""
    return [
        passage
        for passage in passages
        if passage.effective_from <= as_of and (passage.effective_to is None or as_of <= passage.effective_to)
    ]


class CopilotHarness:
    def __init__(
        self,
        *,
        skill: Skill,
        knowledge: list[KnowledgePassage],
        toolbox: MockToolboxService,
        toolbox_url: str,
        model: ScriptedModel,
        sandbox: Sandbox | None = None,
    ) -> None:
        self.skill = skill
        self.knowledge = list(knowledge)
        self.toolbox = toolbox
        self.toolbox_url = toolbox_url
        self.model = model
        self.sandbox = sandbox or Sandbox()
        self.in_force: list[KnowledgePassage] = []
        self.in_force_ids: list[str] = []
        self.catalog: dict[str, dict] = {}
        self._turns = 0
        self._notes: list[str] = []
        self._task = ""

    def start(self, task: str, *, as_of: date) -> HarnessRun:
        self.in_force = select_in_force(self.knowledge, as_of)
        self.in_force_ids = [passage.id for passage in self.in_force]
        self.catalog = {item["name"]: item for item in self.toolbox.tools_list(self.toolbox_url)}
        self._turns = 0
        self._notes = []
        self._task = task
        return self.continue_run(HarnessRun(status="running"))

    def resume(self, run: HarnessRun, *, approved: bool, approver: str) -> HarnessRun:
        if run.status != "awaiting_approval" or not run.pending_tool:
            raise RuntimeError("no pending approval")
        if approved and not approver.strip():
            raise RuntimeError("named approver required")
        tool = run.pending_tool
        arguments = dict(run.pending_arguments)
        run.pending_tool = ""
        run.pending_arguments = {}
        run.trace.append({"kind": "approval", "name": tool, "approved": approved, "by": approver})
        if not approved:
            run.status = "completed"
            run.answer = "Returned to processing. The commitment was not queued."
            run.citation_ids = list(self.in_force_ids)
            return run
        result = self.toolbox.tools_call(self.toolbox_url, tool, arguments)
        run.writes.append(result)
        run.trace.append({"kind": "tool", "name": tool, "approved_by": approver})
        self._notes.append(f"{tool} approved_by={approver} result={result}")
        run.status = "running"
        return self.continue_run(run)

    def continue_run(self, run: HarnessRun) -> HarnessRun:
        """One managed loop. The model proposes; this method allows, pauses or refuses."""
        while run.status == "running":
            if self._turns >= self.sandbox.max_steps:
                run.status = "stopped"
                run.answer = "step budget exhausted"
                return run
            action = self.model.complete(self._context_text())
            self._turns += 1
            run.trace.append({"kind": "model", "action": action.action, "name": action.name})
            if action.action == "final":
                return self._finish(run, action)
            if action.action != "tool":
                run.status = "refused"
                run.answer = f"unsupported action {action.action}"
                return run
            refusal = self._refusal(action)
            if refusal:
                run.status = "refused"
                run.answer = refusal
                run.trace.append({"kind": "refused", "name": action.name, "reason": refusal})
                return run
            spec = self.catalog[action.name]
            arguments = dict(action.arguments)
            if spec["_meta"]["tool_configuration"]["require_approval"] == "always":
                arguments.setdefault(
                    "idempotency_key", f"{arguments.get('loan_id', action.name)}:{action.name}"
                )
                run.status = "awaiting_approval"
                run.pending_tool = action.name
                run.pending_arguments = arguments
                run.trace.append({"kind": "approval_requested", "name": action.name})
                return run
            result = self.toolbox.tools_call(self.toolbox_url, action.name, arguments)
            run.trace.append({"kind": "tool", "name": action.name})
            self._notes.append(f"{action.name}={result}")
        return run

    def _finish(self, run: HarnessRun, action: ModelAction) -> HarnessRun:
        reason = self._citation_problem(action.citation, "final answer")
        if reason:
            run.status = "refused"
            run.answer = reason
            return run
        run.status = "completed"
        run.answer = action.text
        run.citation_ids = [action.citation]
        return run

    def _refusal(self, action: ModelAction) -> str:
        flag = _BUILTIN_SANDBOX.get(action.name)
        if flag is not None and not getattr(self.sandbox, flag):
            return f"sandbox refused {action.name}"
        if action.name not in self.catalog:
            return f"tool {action.name} is not in the toolbox"
        arguments = action.arguments
        if action.name == "queue_commitment" or "citation" in arguments:
            return self._citation_problem(str(arguments.get("citation", "")), action.name)
        return ""

    def _citation_problem(self, citation: str, where: str) -> str:
        if not citation:
            return f"{where} is missing a guideline citation"
        if citation not in self.in_force_ids:
            return f"citation {citation} is not in force"
        return ""

    def _context_text(self) -> str:
        lines = [f"skill: {self.skill.name}", self.skill.body.strip(), "knowledge:"]
        lines.extend(f"{passage.id}: {passage.text}" for passage in self.in_force)
        if self._notes:
            lines.append("notes:")
            lines.extend(self._notes)
        lines.append(f"task: {self._task}")
        return "\n".join(lines)
