"""Offline Toolbox: shared tools behind one managed MCP endpoint.

[verify] Microsoft Learn shows ``AIProjectClient.toolboxes.create_version`` and
``FoundryToolbox`` (from ``agent-framework-foundry-hosting``, imported as
``agent_framework.foundry.FoundryToolbox``). Neither is in the pinned
``azure-ai-projects`` 2.6.1 / ``agent-framework-foundry`` 1.13.1 set, so this
module is a deterministic mock of that shape.

The consumer URL always serves ``default_version``. The developer URL pins a version.
``tools/call`` does not enforce ``require_approval``; the agent runtime must.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from agentplatform.foundry_harness.models import SkillRef, ToolboxTool

# [verify] Ignite 2026 calls out preview tool policies on Toolboxes.
PREVIEW_TOOL_POLICIES: dict[str, str] = {
    "status": "[verify]",
    "rai_policy_name": "lending-default",
    "note": "[verify] preview tool policies; not enforced by this offline mock",
}


@dataclass
class ToolboxVersion:
    name: str
    version: str
    description: str
    tools: list[ToolboxTool]
    skills: list[SkillRef] = field(default_factory=list)
    policies: dict[str, str] = field(default_factory=dict)

    def tool_map(self) -> dict[str, ToolboxTool]:
        return {tool.name: tool for tool in self.tools}


class MockToolboxService:
    """In-memory stand-in for ``project.toolboxes`` plus the MCP endpoint those versions publish."""

    def __init__(self, project_endpoint: str) -> None:
        self.project_endpoint = project_endpoint.rstrip("/")
        self._versions: dict[tuple[str, str], ToolboxVersion] = {}
        self._defaults: dict[str, str] = {}
        self._next: dict[str, int] = {}
        self.call_log: list[tuple[str, str, str]] = []
        self.ledger: dict[str, dict[str, Any]] = {}

    def create_version(
        self,
        name: str,
        *,
        description: str,
        tools: list[ToolboxTool],
        skills: list[SkillRef] | None = None,
        policies: dict[str, str] | None = None,
    ) -> ToolboxVersion:
        """[verify] Mirrors ``project.toolboxes.create_version(name=..., tools=[...])``."""
        if not tools and not skills:
            raise ValueError("a toolbox version needs at least one tool or skill")
        number = self._next.get(name, 0) + 1
        self._next[name] = number
        version = str(number)
        record = ToolboxVersion(
            name=name,
            version=version,
            description=description,
            tools=list(tools),
            skills=list(skills or []),
            policies=dict(policies or {}),
        )
        self._versions[(name, version)] = record
        self._defaults.setdefault(name, version)
        return record

    def promote(self, name: str, version: str) -> None:
        if (name, version) not in self._versions:
            raise KeyError(f"{name} version {version} does not exist")
        self._defaults[name] = version

    def default_version(self, name: str) -> str:
        return self._defaults[name]

    def consumer_endpoint(self, name: str) -> str:
        """Unversioned MCP URL. Always serves the default version."""
        return f"{self.project_endpoint}/toolboxes/{name}/mcp?api-version=v1"

    def developer_endpoint(self, name: str, version: str) -> str:
        """Version-pinned MCP URL, for checking a version before promoting it."""
        return f"{self.project_endpoint}/toolboxes/{name}/versions/{version}/mcp?api-version=v1"

    def tools_list(self, url: str) -> list[dict[str, Any]]:
        """MCP ``tools/list``. Approval metadata is advertised and not enforced here."""
        version = self.resolve(url)
        listed = []
        for tool in version.tools:
            listed.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                    "_meta": {"tool_configuration": {"require_approval": tool.require_approval}},
                }
            )
        return listed

    def tools_call(self, url: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """MCP ``tools/call``. Does not look at ``require_approval``."""
        version = self.resolve(url)
        tool = version.tool_map().get(name)
        if tool is None:
            raise KeyError(name)
        self.call_log.append((version.name, version.version, name))
        return tool.handler(arguments)

    def resolve(self, url: str) -> ToolboxVersion:
        parsed = urlparse(url)
        if parsed.query != "api-version=v1":
            raise ValueError("toolbox MCP url must set api-version=v1")
        parts = [part for part in parsed.path.split("/") if part]
        idx = parts.index("toolboxes")
        name = parts[idx + 1]
        marker = parts[idx + 2]
        if marker == "mcp":
            version = self._defaults[name]
        elif marker == "versions" and parts[idx + 4] == "mcp":
            version = parts[idx + 3]
        else:
            raise ValueError(url)
        try:
            return self._versions[(name, version)]
        except KeyError as exc:
            raise KeyError(f"{name} version {version} is not published") from exc
