"""A2A client: policy check -> kill switch -> JSON-RPC SendMessage with traceparent + tenant ->
schema-validated typed artifact. Foreign agent output is untrusted until validated."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from agentplatform.a2a.registry import DIRECTORY, AgentDirectory
from agentplatform.harness.identity import Principal, child_traceparent, new_traceparent
from agentplatform.harness.tracing import span


class A2AError(RuntimeError):
    def __init__(self, code: str, detail: Any = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class A2AClient:
    def __init__(
        self,
        caller: str,
        directory: AgentDirectory = DIRECTORY,
        transports: dict[str, httpx.AsyncBaseTransport] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.caller, self.directory, self.transports, self.timeout_s = (
            caller,
            directory,
            transports or {},
            timeout_s,
        )

    async def send(
        self,
        callee: str,
        skill: str,
        payload: dict[str, Any],
        principal: Principal,
        traceparent: str | None = None,
    ) -> dict[str, Any]:
        decision = self.directory.authorize(self.caller, callee, principal.tenant_id, skill)
        if not decision.allowed:  # fail closed before any network hop
            raise A2AError("forbidden", decision.reason)
        spec = self.directory.get(callee)
        tp = child_traceparent(traceparent or new_traceparent())
        headers = {
            "A2A-Version": "1.0",
            "traceparent": tp,
            "x-tenant-id": principal.tenant_id,
            "x-caller-agent": self.caller,
            "x-user-subject": principal.subject,
        }
        body = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": uuid.uuid4().hex,
                    "role": "ROLE_USER",
                    "parts": [{"data": {"skill": skill, "input": payload}}],
                }
            },
        }
        transport = self.transports.get(callee)
        with span("a2a.send", callee=callee, skill=skill, tenant=principal.tenant_id, caller=self.caller):
            async with httpx.AsyncClient(transport=transport, timeout=self.timeout_s) as http:
                resp = await http.post(spec.url(), json=body, headers=headers)
        if resp.status_code >= 500:
            raise A2AError("unavailable", resp.status_code)
        data = resp.json()
        if "error" in data:
            raise A2AError("rpc_error", data["error"])
        parts = data.get("result", {}).get("message", {}).get("parts", [])
        out = parts[0].get("data") if parts else None
        if not isinstance(out, dict):
            raise A2AError("schema", "response has no data part")
        if "error" in out:
            raise A2AError(out["error"], out.get("detail"))
        if out.get("status") == "approval_required":
            return out
        if out.get("skill") != skill or not isinstance(out.get("output"), dict):
            raise A2AError("schema", "unexpected artifact shape")
        return out
