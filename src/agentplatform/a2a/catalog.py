"""The agent catalog: first-party custom domain agents + clearly-labelled vendor stand-ins.

Stand-ins imitate the *shape* of vendor prebuilt agents (Dynamics 365-style, Salesforce-style,
SAP-style) so the directory, policy and card contract can be exercised offline. They are NOT vendor
software and make no vendor API calls."""

from __future__ import annotations

from agentplatform.a2a.cards import AgentSpec, SkillSpec

ORCHESTRATOR = "mortgage-underwriting"
BFF = "experience-bff"

CATALOG: tuple[AgentSpec, ...] = (
    AgentSpec(
        id="underwriting-agent",
        name="Underwriting Agent",
        description="Custom domain agent exposing the mortgage underwriting-conditions graph (MAF) over A2A.",
        owner="mortgage-credit-policy",
        version="1.0.0",
        skills=(
            SkillSpec(
                "submit_loan_file",
                "Submit loan file",
                "Start underwriting; returns the HITL review packet (all writes are HITL-gated in the graph).",
                "write-queued",
                ("mortgage", "underwriting"),
            ),
            SkillSpec("get_status", "Get run status", "Status of an underwriting run.", "read"),
        ),
        allowed_callers=(BFF, "salesforce-crm-standin", "dynamics-crm-standin"),
        eval_score=0.93,
        system_of_record="LOS",
        model_deployment="gpt-5-mini",
        prompt_refs=("mortgage.conditions@1.0.0", "mortgage.critic@1.0.0", "mortgage.decision_letter@1.0.0"),
        port=8101,
    ),
    AgentSpec(
        id="crm-agent",
        name="CRM Agent",
        description="Custom domain agent over the CRM (borrower profile, consents, follow-up tasks).",
        owner="crm-platform",
        version="1.2.0",
        skills=(
            SkillSpec(
                "get_borrower_profile",
                "Get borrower profile",
                "Contact prefs, consents, loan officer.",
                "read",
                ("crm",),
            ),
            SkillSpec(
                "create_followup_task",
                "Create follow-up task",
                "Queue a loan-officer task (idempotent).",
                "write-queued",
                ("crm",),
            ),
        ),
        allowed_callers=(ORCHESTRATOR, BFF, "underwriting-agent"),
        eval_score=0.95,
        system_of_record="CRM (Dataverse-style)",
        port=8102,
    ),
    AgentSpec(
        id="erp-agent",
        name="ERP Agent",
        description="Custom domain agent over ERP finance (fee ledger, invoice postings).",
        owner="finance-systems",
        version="1.0.3",
        skills=(
            SkillSpec(
                "get_fee_ledger",
                "Get fee ledger",
                "Appraisal/credit fees billed for a loan.",
                "read",
                ("erp",),
            ),
            SkillSpec(
                "post_fee_invoice",
                "Post fee invoice",
                "Queue a fee invoice posting (idempotent).",
                "write-queued",
                ("erp",),
            ),
        ),
        allowed_callers=(ORCHESTRATOR, "underwriting-agent"),
        eval_score=0.91,
        system_of_record="ERP (GL/AR)",
        port=8103,
    ),
    AgentSpec(
        id="dynamics-crm-standin",
        name="Dynamics 365-style CRM Agent (STAND-IN)",
        description="STAND-IN imitating a Dynamics 365-style prebuilt CRM agent contract. Not Microsoft software.",
        owner="platform-demo",
        version="0.1.0",
        skills=(
            SkillSpec("get_contact", "Get contact", "Contact record by borrower id.", "read"),
            SkillSpec("create_activity", "Create activity", "Queue a phone-call activity.", "write-queued"),
        ),
        allowed_callers=(ORCHESTRATOR, BFF),
        eval_score=0.80,
        stage="staging",
        standin=True,
        vendor_style="Dynamics 365-style",
        system_of_record="CRM",
        port=8104,
    ),
    AgentSpec(
        id="salesforce-crm-standin",
        name="Salesforce-style CRM Agent (STAND-IN)",
        description="STAND-IN imitating a Salesforce-style prebuilt agent contract. Not Salesforce software.",
        owner="platform-demo",
        version="0.1.0",
        skills=(
            SkillSpec("get_lead", "Get lead", "Lead record for a borrower.", "read"),
            SkillSpec("create_task", "Create task", "Queue a follow-up task.", "write-queued"),
        ),
        allowed_callers=(ORCHESTRATOR, BFF),
        eval_score=0.78,
        stage="staging",
        standin=True,
        vendor_style="Salesforce-style",
        system_of_record="CRM",
        port=8105,
    ),
    AgentSpec(
        id="sap-erp-standin",
        name="SAP-style ERP Agent (STAND-IN)",
        description="STAND-IN imitating an SAP-style prebuilt finance agent contract (simulate vs commit). Not SAP software.",
        owner="platform-demo",
        version="0.1.0",
        skills=(
            SkillSpec("get_billing_document", "Get billing document", "Billing document for a loan.", "read"),
            SkillSpec("simulate_posting", "Simulate posting", "Dry-run a GL posting (no commit).", "read"),
            SkillSpec(
                "commit_posting",
                "Commit posting",
                "Commit a GL posting; requires human approval.",
                "write-hitl",
            ),
        ),
        allowed_callers=(ORCHESTRATOR, "erp-agent"),
        eval_score=0.82,
        stage="staging",
        standin=True,
        vendor_style="SAP-style",
        system_of_record="ERP",
        port=8106,
    ),
)


def spec_by_id(agent_id: str) -> AgentSpec:
    for s in CATALOG:
        if s.id == agent_id:
            return s
    raise KeyError(agent_id)
