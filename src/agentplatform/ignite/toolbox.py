"""Foundry Toolbox stand-in: one managed MCP endpoint shared by agents.

The Ignite 2026 post says Toolboxes make tools reusable through a managed MCP endpoint,
with a monitoring dashboard and preview tool policies. Web Search on a Toolbox is described
as coming soon, so it is not registered. Nothing in this module opens a socket.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from agentplatform.ignite.assumptions import MATURITY
from agentplatform.ignite.data import APPLICATIONS

# Preview tool policies. The post does not publish a schema; see ASSUMPTIONS.
TOOL_POLICIES: dict[str, dict[str, Any]] = {
    "get_application": {"side_effect": "read"},
    "pull_bureau": {"side_effect": "read", "requires_consent": True},
    "invoke_a2a_agent": {"side_effect": "read", "maturity": MATURITY["a2a_tool"]},
    "computer_use": {"side_effect": "read", "maturity": MATURITY["computer_use"]},
    "open_browser_session": {"side_effect": "read", "maturity": MATURITY["browser_automation"]},
    "browser_action": {"side_effect": "read", "maturity": MATURITY["browser_automation"]},
    "record_decision": {"side_effect": "write", "requires_approval": True},
}


TOOLBOX_NAME = "loan-underwriting-toolbox"


class LoanToolbox:
    """In-process MCP server. ``server`` is the managed endpoint the harness calls."""

    def __init__(self) -> None:
        self.name = TOOLBOX_NAME
        self.server = MCPServer(
            self.name,
            instructions=(
                "Offline stand-in for a Foundry Toolbox MCP endpoint. Synthetic commercial-loan "
                "tools only. record_decision requires approved_by."
            ),
        )
        self.reports: dict[str, dict] = {}
        self.decisions: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.metrics: dict[str, Any] = {
            "hard_pulls": 0,
            "bookings": 0,
            "blocked_by_policy": 0,
            "calls": {},
        }
        self._register()

    def dashboard(self) -> dict[str, Any]:
        """Stand-in for the Toolbox monitoring dashboard named in the Ignite post."""
        calls = self.metrics["calls"]
        return {
            "calls": dict(calls),
            "hard_pulls": self.metrics["hard_pulls"],
            "bookings": self.metrics["bookings"],
            "blocked_by_policy": self.metrics["blocked_by_policy"],
        }

    def _count(self, name: str) -> None:
        calls: dict[str, int] = self.metrics["calls"]
        calls[name] = calls.get(name, 0) + 1

    def _register(self) -> None:
        box = self

        @self.server.tool()
        def get_application(application_id: str) -> dict:
            """Read one synthetic commercial-loan application."""
            app = APPLICATIONS.get(application_id)
            if app is None:
                raise ToolError("application not found")
            box._count("get_application")
            return dict(app)

        @self.server.tool()
        def pull_bureau(application_id: str, request_id: str) -> dict:
            """Pull a bureau score. The same request_id does not create a second hard pull."""
            app = APPLICATIONS.get(application_id)
            if app is None:
                raise ToolError("application not found")
            if not app["credit_consent"]:
                raise ToolError("no credit-pull consent on file")
            box._count("pull_bureau")
            cached = box.reports.get(request_id)
            if cached is not None:
                return dict(cached)
            report = {
                "request_id": request_id,
                "application_id": application_id,
                "score": app["bureau_score"],
                "permissible_purpose": app["permissible_purpose"],
            }
            box.reports[request_id] = report
            box.metrics["hard_pulls"] += 1
            return dict(report)

        @self.server.tool()
        def invoke_a2a_agent(agent_name: str, message: str) -> dict:
            """GA A2A tool stand-in. Connects to one local agent. No network call."""
            if agent_name != "relationship-manager":
                raise ToolError("agent is not connected to this toolbox")
            app = APPLICATIONS.get(message.strip())
            if app is None:
                raise ToolError("unknown application")
            box._count("invoke_a2a_agent")
            return {
                "agent_name": agent_name,
                "maturity": MATURITY["a2a_tool"],
                "stand_in": True,
                "transport": "in-process",
                "exposure": app["relationship_exposure"],
            }

        @self.server.tool()
        def computer_use(instruction: str) -> dict:
            """GA computer-use stand-in. Returns a scripted observation and drives nothing."""
            box._count("computer_use")
            return {
                "maturity": MATURITY["computer_use"],
                "drove_desktop": False,
                "observation": "LOS desktop shows the application in review. No desktop was driven.",
                "instruction": instruction,
            }

        @self.server.tool()
        def open_browser_session(purpose: str) -> dict:
            """GA browser automation: isolated session, Live View, customer-owned recording label."""
            session_id = "br-" + "-".join(purpose.lower().split())
            record = {
                "session_id": session_id,
                "isolated": True,
                "live_view": True,
                "take_control_available": True,
                "recording_uri": f"customer-storage://recordings/{session_id}",
                "private_network_access": MATURITY["browser_private_network"],
                "fetched_url": False,
                "maturity": MATURITY["browser_automation"],
                "purpose": purpose,
            }
            box.sessions[session_id] = record
            box._count("open_browser_session")
            return dict(record)

        @self.server.tool()
        def browser_action(session_id: str, action: str) -> dict:
            """Read a scripted page, or ask a person to take control of the session."""
            if session_id not in box.sessions:
                raise ToolError("unknown browser session")
            box._count("browser_action")
            if action == "read_portal":
                return {
                    "session_id": session_id,
                    "take_control_required": False,
                    "text": "Investor portal: insurance binder not on file.",
                    "fetched_url": False,
                }
            if action == "take_control":
                return {
                    "session_id": session_id,
                    "take_control_required": True,
                    "live_view": True,
                    "fetched_url": False,
                }
            raise ToolError("action not allowed")

        @self.server.tool()
        def record_decision(
            application_id: str, decision: str, approved_by: str, idempotency_key: str
        ) -> dict:
            """Book a decision. Refuses a write that does not name the approving officer."""
            if not approved_by.strip():
                raise ToolError("approved_by is required")
            if application_id not in APPLICATIONS:
                raise ToolError("application not found")
            box._count("record_decision")
            existing = box.decisions.get(idempotency_key)
            if existing is not None:
                return dict(existing)
            ticket = {
                "application_id": application_id,
                "decision": decision,
                "approved_by": approved_by,
                "idempotency_key": idempotency_key,
                "ticket": f"BK-{application_id}",
            }
            box.decisions[idempotency_key] = ticket
            box.metrics["bookings"] += 1
            return dict(ticket)
