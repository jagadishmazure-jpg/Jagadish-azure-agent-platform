"""A2A server factory (a2a-sdk 1.x). Every inbound task is checked for tenant + caller headers,
authorized against the directory (defense in depth behind APIM), kill-switch checked, and traced
with the caller's traceparent so spans stitch across agents in App Insights."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from a2a.helpers.proto_helpers import get_data_parts, new_data_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI

from agentplatform.a2a.cards import AgentSpec, card_json, to_agent_card
from agentplatform.a2a.registry import DIRECTORY, AgentDirectory
from agentplatform.harness.identity import trace_id_of
from agentplatform.harness.tracing import span


@dataclass(frozen=True)
class CallContext:
    tenant: str
    caller: str
    traceparent: str
    subject: str = ""


SkillHandler = Callable[[str, dict[str, Any], CallContext], Awaitable[dict[str, Any]]]
REQUIRED_HEADERS = ("x-tenant-id", "x-caller-agent", "traceparent")


class DomainAgentExecutor(AgentExecutor):
    def __init__(self, spec: AgentSpec, handler: SkillHandler, directory: AgentDirectory) -> None:
        self.spec, self.handler, self.directory = spec, handler, directory

    async def execute(self, context, event_queue) -> None:
        headers = {
            k.lower(): v
            for k, v in (
                context.call_context.state.get("headers", {}) if context.call_context else {}
            ).items()
        }

        async def reply(payload: dict[str, Any]) -> None:
            await event_queue.enqueue_event(
                new_data_message(payload, context_id=context.context_id, task_id=context.task_id)
            )

        missing = [h for h in REQUIRED_HEADERS if not headers.get(h)]
        if missing:
            await reply({"error": "missing_headers", "detail": missing})
            return
        parts = get_data_parts(context.message.parts) if context.message else []
        body = parts[0] if parts and isinstance(parts[0], dict) else {}
        skill, args = body.get("skill", ""), body.get("input", {}) or {}
        ctx = CallContext(
            headers["x-tenant-id"],
            headers["x-caller-agent"],
            headers["traceparent"],
            headers.get("x-user-subject", ""),
        )
        decision = self.directory.authorize(ctx.caller, self.spec.id, ctx.tenant, skill)
        if not decision.allowed:
            await reply({"error": "forbidden", "detail": decision.reason})
            return
        s = self.spec.skill(skill)
        if s and s.side_effect == "write-hitl" and not args.get("approved_by"):
            await reply(
                {"skill": skill, "status": "approval_required", "trace_id": trace_id_of(ctx.traceparent)}
            )
            return
        with span(
            f"a2a.{self.spec.id}.{skill}",
            tenant=ctx.tenant,
            caller=ctx.caller,
            parent_trace=trace_id_of(ctx.traceparent),
            standin=self.spec.standin,
        ):
            try:
                output = await self.handler(skill, args, ctx)
            except Exception as exc:  # typed error back to the caller, never a stack trace
                await reply({"error": "skill_failed", "detail": type(exc).__name__, "skill": skill})
                return
        await reply(
            {
                "skill": skill,
                "output": output,
                "agent": self.spec.id,
                "trace_id": trace_id_of(ctx.traceparent),
            }
        )

    async def cancel(self, context, event_queue) -> None:
        return None


def create_a2a_app(spec: AgentSpec, handler: SkillHandler, directory: AgentDirectory = DIRECTORY) -> FastAPI:
    card = to_agent_card(spec)
    request_handler = DefaultRequestHandler(
        agent_executor=DomainAgentExecutor(spec, handler, directory),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(title=spec.name, version=spec.version)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=[
            *create_agent_card_routes(card),  # canonical: /.well-known/agent-card.json
            *create_agent_card_routes(
                card, card_url="/.well-known/agent.json"
            ),  # legacy alias (pre-0.3 path)
        ],
        jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/a2a"),
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "agent": spec.id, "killed": directory.kill_switch.is_tripped(spec.id)}

    @app.get("/card")
    async def card_view() -> dict:
        return card_json(spec)

    return app
