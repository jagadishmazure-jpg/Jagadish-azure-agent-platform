"""HR policy agent: one MAF Agent + one retrieval tool over the HR index.

Temporal + ACL filtering is applied in the tool (i.e. as a Search filter), not by the model:
the model never sees a passage the caller isn't entitled to or that isn't in force."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from agent_framework import Agent, ChatResponse, Message, tool

from agentplatform.harness.identity import Principal
from agentplatform.harness.tracing import span
from agentplatform.knowledge.search import SearchBackend, SearchQuery, get_search_backend
from agentplatform.llm.clients import MockChatClient, get_chat_client
from agentplatform.prompts import load_pack
from agentplatform.prompts.schemas import PolicyAnswer
from agentplatform.safety.content_safety import get_safety_gate

PROMPT = load_pack().get("hr.policy")
MIN_SCORE = 0.02


def make_search_tool(backend: SearchBackend, principal: Principal, as_of: date):
    @tool(name="search_hr_policy", description="Search HR policy passages in force for the caller.")
    def search_hr_policy(query: str) -> str:
        hits = backend.search(SearchQuery(query, as_of, principal.groups, top=3))
        docs = [
            {"id": h.chunk.id, "title": h.chunk.title, "content": h.chunk.content, "score": round(h.score, 4)}
            for h in hits
            if h.score >= MIN_SCORE
        ]
        gate = get_safety_gate()
        docs = [
            d
            for d, v in zip(docs, gate.check_documents([d["content"] for d in docs]), strict=True)
            if v.allowed
        ]
        return json.dumps(docs)

    return search_hr_policy


def _offline_answer(messages: list[Message], options: dict[str, Any]) -> ChatResponse | None:
    """Deterministic 'model' for offline runs: compose a cited answer from the top passage."""
    results = [c for m in messages for c in m.contents if c.type == "function_result"]
    if not results or options.get("response_format") is not PolicyAnswer:
        return None
    docs = json.loads(str(results[-1].result) or "[]")
    if not docs:
        ans = PolicyAnswer(
            answer="I couldn't find an HR policy covering that; routing you to HR.",
            citations=[],
            limited=True,
        )
    else:
        top = docs[0]
        ans = PolicyAnswer(answer=f"{top['content']} (per '{top['title']}')", citations=[top["id"]])
    return ChatResponse(messages=[Message(role="assistant", contents=[ans.model_dump_json()])])


def build_hr_agent(
    principal: Principal, as_of: date | None = None, backend: SearchBackend | None = None
) -> Agent:
    client = get_chat_client()
    if isinstance(client, MockChatClient):
        client.script = _offline_answer
    return Agent(
        client=client,
        name="hr-policy-agent",
        instructions=PROMPT.body,
        tools=[
            make_search_tool(backend or get_search_backend("hr_policies"), principal, as_of or date.today())
        ],
        additional_properties={"prompt_ref": PROMPT.ref},
    )


async def ask_hr(question: str, principal: Principal, as_of: date | None = None) -> PolicyAnswer:
    verdict = get_safety_gate().check_inbound(question)
    if not verdict.allowed:
        return PolicyAnswer(answer="Request blocked by content safety.", citations=[], limited=True)
    with span("hr.ask", tenant=principal.tenant_id, prompt=PROMPT.ref):
        res = await build_hr_agent(principal, as_of).run(question, options={"response_format": PolicyAnswer})
    ans: PolicyAnswer = res.value
    # Groundedness guard: any cited id must be a passage the tool actually returned.
    returned = {
        d["id"]
        for m in res.messages
        for c in m.contents
        if c.type == "function_result"
        for d in json.loads(str(c.result) or "[]")
    }
    if not set(ans.citations) <= returned:
        return PolicyAnswer(
            answer="I can't answer that reliably; routing you to HR.", citations=[], limited=True
        )
    return ans
