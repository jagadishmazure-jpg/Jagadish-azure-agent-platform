"""The cast shared by every orchestration: three specialists, an underwriter, a reviewer and a triage agent.

Each role is a real MAF `Agent`. Offline, its client is a `MockChatClient` driven by a small deterministic
script (below) that behaves like a well-instructed model: call the facts tool, report findings in a fixed
format, hand off or conclude. With `AAP_MODE=azure` the same agents run on Foundry via `get_chat_client()`
and the instructions carry the format. Numbers only ever come from the facts tools."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from agent_framework import Agent, BaseChatClient, ChatResponse, Content, Message, tool

from agentplatform.config import get_settings
from agentplatform.llm.clients import MockChatClient, get_chat_client
from agentplatform.orchestrations.facts import FLAG_CATALOG, LANES

FLAGS_RE = re.compile(r"FLAGS:\s*([a-z_, ]*)")
CONDITIONS_RE = re.compile(r"CONDITIONS:\s*([a-z_, ]*)")
DECISION_RE = re.compile(r"DECISION:\s*([a-z_]+)")
ROUTE_RE = re.compile(r"ROUTE:\s*([a-z_, ]*)")
MISSING_RE = re.compile(r"(?:(?<![A-Z_])MISSING|ADD):\s*([a-z_, ]*)")
MISSING_LANES_RE = re.compile(r"MISSING_LANES:\s*([a-z_, ]*)")

FORMAT = (
    "Use only facts returned by your tools; never compute or invent numbers. "
    "End your message with one line `FLAGS: <comma-separated flag ids or none>`."
)
INSTRUCTIONS = {
    "income": f"You are the income analyst for a mortgage conditions review. Call get_income_facts. {FORMAT}",
    "credit": f"You are the credit analyst. Call get_credit_facts and report score, DTI and inquiries. {FORMAT}",
    "assets": f"You are the assets analyst. Call get_assets_facts; report funds to close and reserves. {FORMAT}",
    "underwriter": (
        "You are the underwriter. Collect every FLAGS line from the specialists (and any flag a reviewer or "
        "human asks you to ADD) and reply with `CONDITIONS: <flags or none>` then "
        "`DECISION: approve | approve_with_conditions | refer` (refer if dti_over_limit or insufficient_funds)."
    ),
    "reviewer": (
        "You are the compliance reviewer (checker). Call get_all_flags and compare with the underwriter's "
        "CONDITIONS line. Reply `APPROVED` if complete, else `MISSING: <flags>`."
    ),
    "triage": (
        "You are the intake triage agent. Call screen_loan to see which lanes have findings, say "
        "`ROUTE: <lanes>` and hand off to the first lane (or to the underwriter if none). If no loan id is "
        "given, ask the user for it."
    ),
}
DESCRIPTIONS = {
    "income": "Income analyst: qualifying income and income stability.",
    "credit": "Credit analyst: tri-merge score, liabilities, DTI and recent inquiries.",
    "assets": "Assets analyst: funds to close, large deposits and reserves.",
    "underwriter": "Underwriter: consolidates findings into conditions and a decision.",
    "reviewer": "Compliance reviewer: checks the underwriter's conditions against the facts.",
    "triage": "Intake triage: screens the file and routes to the right specialists.",
}


def parse_list(regex: re.Pattern[str], text: str) -> list[str]:
    out: list[str] = []
    for m in regex.finditer(text or ""):
        out += [x.strip() for x in m.group(1).split(",") if x.strip() and x.strip() != "none"]
    return out


def decision_for(flags: list[str]) -> str:
    if not flags:
        return "approve"
    if {"dti_over_limit", "insufficient_funds"} & set(flags):
        return "refer"
    return "approve_with_conditions"


def verdict(flags: list[str]) -> str:
    flags = sorted(set(flags))
    return f"CONDITIONS: {', '.join(flags) or 'none'}\nDECISION: {decision_for(flags)}"


# ------------------------------------------------------------------------------------------ mock scripts
def _txt(text: str, *calls: Content) -> ChatResponse:
    return ChatResponse(
        messages=[Message(role="assistant", contents=[text, *calls] if text else list(calls))],
        model="mock-deterministic",
    )


def _call(name: str, **args: Any) -> Content:
    return Content.from_function_call(uuid.uuid4().hex[:8], name, arguments=args)


def _tool_names(options: dict[str, Any]) -> list[str]:
    return [getattr(t, "name", "") for t in (options.get("tools") or [])]


def _result_of(msgs: list[Message], tool_name: str) -> Any | None:
    ids = {c.call_id for m in msgs for c in m.contents if c.type == "function_call" and c.name == tool_name}
    for m in reversed(msgs):
        for c in m.contents:
            if c.type == "function_result" and c.call_id in ids:
                return json.loads(str(c.result))
    return None


def _handoff(options: dict[str, Any], msgs: list[Message], me: str) -> Content | None:
    """Pick the next hop from the triage ROUTE line: next unvisited lane, else the underwriter."""
    tools = _tool_names(options)
    if not any(t.startswith("handoff_to_") for t in tools):
        return None
    text = "\n".join(m.text or "" for m in msgs if m.role == "assistant")
    route = parse_list(ROUTE_RE, text)
    done = {m.author_name for m in msgs if m.role == "assistant" and "FLAGS:" in (m.text or "")} | {me}
    nxt = next((lane for lane in route if lane not in done), "underwriter")
    return _call(f"handoff_to_{nxt}") if f"handoff_to_{nxt}" in tools else None


def specialist_script(lane: str, *, down: bool = False) -> Callable:
    summaries = {
        "income": lambda f: f"Qualifying income ${f['monthly_qualifying_income']:,.2f}/mo ({f['method']}).",
        "credit": lambda f: (
            f"Score {f['representative_score']} ({f['report_id']}); liabilities "
            f"${f['monthly_liabilities']:,}/mo; DTI {f['dti']:.2%}; recent inquiries {len(f['recent_inquiries'])}."
        ),
        "assets": lambda f: (
            f"Usable assets ${f['usable_assets']:,.0f} vs funds to close ${f['funds_to_close']:,.0f}; "
            f"reserves {f['reserves_months']} months; large deposits {len(f['large_deposits'])}."
        ),
    }

    def script(msgs: list[Message], options: dict[str, Any]) -> ChatResponse:
        if down:  # chaos: the specialist's model returns nothing useful
            return _txt(f"{lane} analyst unavailable: no findings.")
        facts = _result_of(msgs, f"get_{lane}_facts")
        if facts is None:
            return _txt("", _call(f"get_{lane}_facts"))
        body = f"{summaries[lane](facts)}\nFLAGS: {', '.join(facts['flags']) or 'none'}"
        hop = _handoff(options, msgs, lane)
        return _txt(body, hop) if hop else _txt(body)

    return script


def underwriter_script(msgs: list[Message], options: dict[str, Any]) -> ChatResponse:
    found: list[str] = []
    reported: set[str] = set()
    silent: set[str] = set()
    for m in msgs:
        if m.role == "assistant" and m.author_name in LANES:
            if "FLAGS:" in (m.text or ""):
                reported.add(m.author_name)
                found += parse_list(FLAGS_RE, m.text)
            elif m.text:
                silent.add(m.author_name)
        elif m.role == "user" or m.author_name == "reviewer":
            found += parse_list(MISSING_RE, m.text)
        if m.author_name not in LANES:  # a manager/human can carry a failed lane forward (e.g. after a reset)
            silent.update(x for x in parse_list(MISSING_LANES_RE, m.text) if x in LANES)
    text = verdict([f for f in found if f in FLAG_CATALOG])
    if missing := sorted(silent - reported):  # a lane spoke but produced no findings: never approve blind
        text = text.rsplit("DECISION:", 1)[0] + f"DECISION: refer\nMISSING_LANES: {', '.join(missing)}"
    return _txt(text)


def reviewer_script(*, never_satisfied: bool = False) -> Callable:
    def script(msgs: list[Message], options: dict[str, Any]) -> ChatResponse:
        truth = _result_of(msgs, "get_all_flags")
        if truth is None:
            return _txt("", _call("get_all_flags"))
        last = next((m.text for m in reversed(msgs) if m.author_name == "underwriter"), "")
        missing = sorted(set(truth) - set(parse_list(CONDITIONS_RE, last)))
        if never_satisfied:  # chaos: a checker that always finds something
            return _txt("MISSING: low_reserves")
        return _txt(f"MISSING: {', '.join(missing)}" if missing else "APPROVED")

    return script


def triage_script(msgs: list[Message], options: dict[str, Any]) -> ChatResponse:
    user = next((m.text for m in msgs if m.role == "user" and re.search(r"L-\d{4}", m.text or "")), None)
    if user is None:
        return _txt("Which loan should I review? Please give the loan id (e.g. L-1001).")
    screen = _result_of(msgs, "screen_loan")
    if screen is None:
        return _txt("", _call("screen_loan"))
    route = [lane for lane in LANES if screen[lane]]
    target = route[0] if route else "underwriter"
    return _txt(f"ROUTE: {', '.join(route) or 'none'}", _call(f"handoff_to_{target}"))


SCRIPTS: dict[str, Callable] = {
    "underwriter": underwriter_script,
    "triage": triage_script,
}


# ------------------------------------------------------------------------------------------------ roster
class Roster:
    """Builds agents over one fact sheet and counts model calls (offline) for the comparison."""

    def __init__(self, facts: dict[str, Any], *, faults: set[str] | None = None) -> None:
        self.facts = facts
        self.faults = faults or set()
        self.clients: list[BaseChatClient] = []
        self.azure = get_settings().azure

    @property
    def llm_calls(self) -> int:
        return sum(getattr(c, "calls", 0) for c in self.clients)

    def client(self, script: Callable | None) -> BaseChatClient:
        c = get_chat_client() if self.azure else MockChatClient(script=script)
        self.clients.append(c)
        return c

    def tools(self, role: str) -> list:
        f = self.facts
        if role in LANES:

            @tool(
                name=f"get_{role}_facts", description=f"Deterministic {role} facts for the loan under review."
            )
            def lane_facts() -> str:
                return json.dumps(f[role])

            return [lane_facts]
        if role == "reviewer":

            @tool(name="get_all_flags", description="All flags the deterministic rules raise for this loan.")
            def get_all_flags() -> str:
                return json.dumps(sorted(x for lane in LANES for x in f[lane]["flags"]))

            return [get_all_flags]
        if role == "triage":

            @tool(name="screen_loan", description="Which lanes raise at least one flag for this loan.")
            def screen_loan() -> str:
                return json.dumps({lane: bool(f[lane]["flags"]) for lane in LANES})

            return [screen_loan]
        return []

    def script(self, role: str) -> Callable:
        if role in LANES:
            return specialist_script(role, down=f"{role}_down" in self.faults)
        if role == "reviewer":
            return reviewer_script(never_satisfied="looping_reviewer" in self.faults)
        return SCRIPTS[role]

    def agent(self, role: str, *, handoff: bool = False) -> Agent:
        return Agent(
            client=self.client(self.script(role)),
            name=role,
            instructions=INSTRUCTIONS[role],
            description=DESCRIPTIONS[role],
            tools=self.tools(role),
            # HandoffBuilder.build() rejects agents without this flag (MAF 1.2).
            require_per_service_call_history_persistence=handoff,
        )

    def agents(self, *roles: str, handoff: bool = False) -> dict[str, Agent]:
        return {r: self.agent(r, handoff=handoff) for r in roles}
