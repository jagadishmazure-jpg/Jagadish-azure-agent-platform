"""Bank-supplied skills for the commercial-loan agent.

The harness calls these in order. It does not contain the credit policy or the payment formula.
"""

from __future__ import annotations

from decimal import Decimal

from agentplatform.ignite.data import AGENT_INSTRUCTIONS, CREDIT_POLICY, KnowledgeItem
from agentplatform.ignite.harness import AgentDefinition, HarnessError, Skill, SkillContext
from agentplatform.ignite.money import debt_service_coverage, monthly_payment
from agentplatform.ignite.toolbox import TOOLBOX_NAME


class AssembleFile(Skill):
    name = "assemble_file"
    requires_approval = False

    async def run(self, ctx: SkillContext) -> None:
        application = await ctx.call_tool("get_application", {"application_id": ctx.application_id})
        bureau = await ctx.call_tool(
            "pull_bureau",
            {"application_id": ctx.application_id, "request_id": f"bureau-{ctx.application_id}"},
        )
        exposure = await ctx.call_tool(
            "invoke_a2a_agent",
            {"agent_name": "relationship-manager", "message": ctx.application_id},
        )
        desktop = await ctx.call_tool(
            "computer_use", {"instruction": f"Read LOS notes for {ctx.application_id}"}
        )
        session = await ctx.call_tool("open_browser_session", {"purpose": "investor portal insurance check"})
        portal = await ctx.call_tool(
            "browser_action", {"session_id": session["session_id"], "action": "read_portal"}
        )
        ctx.state["application"] = application
        ctx.state["bureau"] = bureau
        ctx.state["exposure"] = exposure
        ctx.state["desktop"] = desktop
        ctx.state["browser"] = {
            "session_id": session["session_id"],
            "isolated": session["isolated"],
            "recording_uri": session["recording_uri"],
            "fetched_url": session["fetched_url"],
            "private_network_access": session["private_network_access"],
            "portal": portal["text"],
        }


class ProposeDecision(Skill):
    name = "propose_decision"
    requires_approval = False

    async def run(self, ctx: SkillContext) -> None:
        policy = ctx.knowledge.get("CREDIT-POLICY-SMB")
        if policy is None or not policy.min_dscr:
            raise HarnessError("credit policy knowledge was not supplied")
        application = ctx.state["application"]
        payment = monthly_payment(
            Decimal(application["principal"]),
            Decimal(application["annual_rate"]),
            int(application["term_months"]),
        )
        coverage = debt_service_coverage(
            Decimal(application["monthly_noi"]),
            Decimal(application["existing_debt_service"]),
            payment,
        )
        minimum = Decimal(policy.min_dscr)
        ctx.state["payment"] = str(payment)
        ctx.state["dscr"] = str(coverage)
        ctx.state["policy_id"] = policy.id
        if coverage >= minimum:
            ctx.state["proposed_decision"] = "approve_with_conditions"
            ctx.state["conditions"] = [f"Insurance binder before booking ({policy.id})"]
        else:
            ctx.state["proposed_decision"] = "refer"
            ctx.state["conditions"] = [f"DSCR {coverage} is below {minimum} ({policy.id})"]


class CommitDecision(Skill):
    name = "commit_decision"
    requires_approval = True

    async def run(self, ctx: SkillContext) -> None:
        decision = ctx.approval
        if decision is None:
            raise HarnessError("commit requires an officer decision")
        ctx.state["officer_id"] = decision.officer_id
        ctx.state["officer_approved"] = decision.approved
        ctx.state["officer_reason"] = decision.reason
        if not decision.approved:
            ctx.state["booked"] = False
            ctx.state["outcome"] = "declined"
            return
        booking = await ctx.call_tool(
            "record_decision",
            {
                "application_id": ctx.application_id,
                "decision": ctx.state["proposed_decision"],
                "approved_by": decision.officer_id,
                "idempotency_key": f"book-{ctx.application_id}",
            },
        )
        ctx.state["booked"] = True
        ctx.state["outcome"] = ctx.state["proposed_decision"]
        ctx.state["booking"] = booking


def commercial_loan_agent(
    *,
    knowledge: tuple[KnowledgeItem, ...] | None = None,
    skills: tuple[Skill, ...] | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        name="commercial-loan-agent",
        instructions=AGENT_INSTRUCTIONS,
        knowledge=(CREDIT_POLICY,) if knowledge is None else knowledge,
        skills=(AssembleFile(), ProposeDecision(), CommitDecision()) if skills is None else skills,
        toolbox_name=TOOLBOX_NAME,
        voice_enabled=False,
    )
