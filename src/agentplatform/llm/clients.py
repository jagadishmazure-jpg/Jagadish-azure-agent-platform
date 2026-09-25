"""Model access. Offline: deterministic MockChatClient (a real MAF BaseChatClient, so Agents, tools,
structured output and middleware behave exactly as with Foundry). Azure: FoundryChatClient over the
Foundry project endpoint with managed identity; optional fallback deployment for 429/5xx."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, Content, Message
from agent_framework._tools import FunctionInvocationLayer

from agentplatform.config import Settings, azure_credential, get_settings

Script = Callable[[list[Message], dict[str, Any]], ChatResponse | None]


def _json_block(text: str) -> dict | None:
    """Pull the first JSON object out of a prompt (executors send facts + a deterministic draft)."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


class MockChatClient(FunctionInvocationLayer, BaseChatClient):
    """Deterministic stand-in for Azure OpenAI / Foundry.

    Behaviour, in order:
      1. `script` hook (tests / single-agent demos) may return a full ChatResponse.
      2. If tools are offered and none has been called yet, call the first tool with {"query": user text}.
      3. If a `response_format` is requested and the prompt carries a JSON `draft`, return the draft
         (numbers and citations always come from tools; the model only polishes wording).
      4. Otherwise echo a grounded summary of the last tool result or user message.
    """

    OTEL_PROVIDER_NAME = "mock"

    def __init__(self, script: Script | None = None, fail_times: int = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.script = script
        self.fail_times = fail_times
        self.calls = 0

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):  # type: ignore[override]
        self.calls += 1
        if self.calls <= self.fail_times:
            from agentplatform.harness.resilience import TransientError

            raise TransientError("mock 429 Too Many Requests")
        msgs = list(messages)
        if self.script is not None:
            scripted = self.script(msgs, dict(options))
            if scripted is not None:
                return scripted
        tool_results = [c for m in msgs for c in m.contents if c.type == "function_result"]
        tools = options.get("tools") or []
        user_text = next((m.text for m in reversed(msgs) if m.role == "user"), "")
        if tools and not tool_results:
            first = tools[0]
            name = getattr(first, "name", None) or getattr(first, "__name__", "tool")
            call = Content.from_function_call(uuid.uuid4().hex[:8], name, arguments={"query": user_text})
            return ChatResponse(messages=[Message(role="assistant", contents=[call])])
        fmt = options.get("response_format")
        payload = _json_block(user_text) or {}
        if fmt is not None and "draft" in payload:
            text = json.dumps(payload["draft"])
        elif tool_results:
            text = str(tool_results[-1].result)
        else:
            text = f"[mock] {user_text[:400]}"
        return ChatResponse(
            messages=[Message(role="assistant", contents=[text])],
            model="mock-deterministic",
        )


def get_chat_client(settings: Settings | None = None, *, fallback: bool = False) -> BaseChatClient:
    s = settings or get_settings()
    if not s.azure:
        return MockChatClient()
    from agent_framework_foundry import FoundryChatClient

    model = s.foundry_fallback_model if (fallback and s.foundry_fallback_model) else s.foundry_model
    return FoundryChatClient(
        project_endpoint=s.foundry_project_endpoint,
        model=model,
        credential=azure_credential(s),
    )
