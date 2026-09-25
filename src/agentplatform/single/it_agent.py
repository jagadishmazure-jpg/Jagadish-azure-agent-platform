"""IT service desk agent: one MAF Agent, a read tool, a queued-write tool, and an
approval-gated write tool (`approval_mode="always_require"`).

The approval request surfaces as `response.user_input_requests`; the caller (BFF / Teams card) returns
a function-approval response. Nothing privileged runs on the model's say-so."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Agent, AgentSession, ChatResponse, Content, Message, tool

from agentplatform.harness.identity import Principal
from agentplatform.llm.clients import MockChatClient, get_chat_client
from agentplatform.prompts import load_pack
from agentplatform.prompts.schemas import TicketTriage

PROMPT = load_pack().get("it.servicedesk")

KB = {
    "KB-VPN-01": "VPN fails after password change: sign out of the VPN client and sign back in with the new password.",
    "KB-PWD-02": "Password resets require identity verification and service-desk approval; users get a temporary password.",
    "KB-LAP-03": "Laptop won't boot: hold power 15s, connect charger, then run hardware diagnostics (F12).",
}


@dataclass
class ITDesk:
    """Side-effect sinks (would be ServiceNow / Entra ID Graph calls behind APIM in Azure)."""

    tickets: dict[str, dict] = field(default_factory=dict)
    resets: list[str] = field(default_factory=list)

    def tools(self, principal: Principal) -> list:
        @tool(name="search_kb", description="Search the IT knowledge base.")
        def search_kb(query: str) -> str:
            q = set(query.lower().split())
            hits = [
                {"id": k, "text": v} for k, v in KB.items() if q & set(v.lower().replace(":", " ").split())
            ]
            return json.dumps(hits[:2])

        @tool(name="create_ticket", description="Create a service desk ticket (queued write, idempotent).")
        def create_ticket(summary: str, priority: str = "P3") -> str:
            key = f"{principal.subject}:{summary}"
            t = self.tickets.setdefault(
                key,
                {
                    "id": f"INC{len(self.tickets) + 1:05d}",
                    "summary": summary,
                    "priority": priority,
                    "requester": principal.subject,
                },
            )
            return json.dumps(t)

        @tool(
            name="reset_password",
            description="Reset a user's password. Requires human approval.",
            approval_mode="always_require",
        )
        def reset_password(user_id: str) -> str:
            self.resets.append(user_id)
            return json.dumps({"user_id": user_id, "status": "temporary password issued"})

        return [search_kb, create_ticket, reset_password]


def _offline_policy(messages: list[Message], options: dict[str, Any]) -> ChatResponse | None:
    """Deterministic 'model': KB lookup → (password? request approval-gated reset) → triage JSON."""
    called = [c.name for m in messages for c in m.contents if c.type == "function_call"]
    results = [c for m in messages for c in m.contents if c.type == "function_result"]
    user = next((m.text for m in messages if m.role == "user" and m.text), "")
    password = "password" in user.lower()

    def call(name: str, **args: Any) -> ChatResponse:
        c = Content.from_function_call(uuid.uuid4().hex[:8], name, arguments=args)
        return ChatResponse(messages=[Message(role="assistant", contents=[c])])

    if "search_kb" not in called:
        return call("search_kb", query=user)
    if password and "reset_password" not in called:
        return call("reset_password", user_id=user.split()[-1].strip("?.") if "for" in user else "self")
    if not password and "create_ticket" not in called:
        return call("create_ticket", summary=user[:80], priority="P3")
    kb_ids = [
        d["id"] for r in results for d in (json.loads(str(r.result)) if str(r.result).startswith("[") else [])
    ]
    rejected = any("reject" in str(r.result).lower() for r in results)
    triage = TicketTriage(
        category="access" if password else "hardware/software",
        priority="P2" if password else "P3",
        next_action=(
            "password reset declined by approver; ticket routed to identity team"
            if rejected
            else "temporary password issued"
            if password
            else "ticket created; follow KB steps"
        ),
        requires_approval=password,
        citations=kb_ids,
    )
    return ChatResponse(messages=[Message(role="assistant", contents=[triage.model_dump_json()])])


def build_it_agent(principal: Principal, desk: ITDesk) -> Agent:
    client = get_chat_client()
    if isinstance(client, MockChatClient):
        client.script = _offline_policy
    return Agent(
        client=client, name="it-servicedesk-agent", instructions=PROMPT.body, tools=desk.tools(principal)
    )


async def run_it(
    request: str, principal: Principal, desk: ITDesk, approver: str | None = None, approve: bool = False
) -> dict[str, Any]:
    agent = build_it_agent(principal, desk)
    session = AgentSession()
    res = await agent.run(request, session=session, options={"response_format": TicketTriage})
    approvals = []
    while res.user_input_requests:
        replies = []
        for req in res.user_input_requests:
            ok = bool(approve and approver)
            approvals.append({"tool": req.function_call.name, "approved": ok, "approver": approver})
            replies.append(req.to_function_approval_response(approved=ok))
        res = await agent.run(
            Message(role="user", contents=replies), session=session, options={"response_format": TicketTriage}
        )
    return {"triage": res.value.model_dump() if res.value else None, "approvals": approvals}
