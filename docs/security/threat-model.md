# Threat model

This repository is a mortgage underwriting platform on Microsoft Agent Framework: a FastAPI BFF (the
only externally reachable app, behind APIM), a checkpointed MAF workflow with a critic and a human
underwriter, A2A agents (underwriting, CRM, ERP) governed by a directory with a kill switch, small
read-only MCP tool servers, temporal and access-controlled retrieval (AI Search), Document
Intelligence extraction and a Content Safety gate. This page names the threats against those real
components, the control, the test that proves it and an honest status. **Built** means in the code and
tested offline. **Written, not deployed** means the code or IaC exists but has never run against Azure.
**Planned** means it does not exist yet. Nothing here has been deployed.

Frameworks used: STRIDE for the system, the OWASP Top 10 for LLM Applications 2025 for the model-facing parts, and MITRE ATLAS for
adversary techniques against AI systems.

## System and trust boundaries

```mermaid
flowchart LR
  U[loan officer / applicant docs] -->|HTTPS via APIM| BFF[BFF]
  DOCS[pay stubs, W-2s, bank statements] -.->|untrusted| DI[Document Intelligence]
  BFF --> CS[Content Safety gate]
  BFF --> WF[MAF mortgage workflow + checkpoints]
  WF -->|prompt| LLM[Foundry model or mock]
  WF --> KS[AI Search: temporal + ACL]
  WF -->|A2A| A2A[underwriting / CRM / ERP agents]
  A2A --> DIR[directory: policy, promotion, kill switch]
  WF -->|MCP| MCP[read-only MCP servers]
  WF --> HITL[human underwriter]
  HITL --> OUT[outbox: decision letter, LOS queue]
```

Boundaries that matter: applicant documents and their extracted text (attacker-influenced); the
model's draft becoming a condition or a letter; one agent calling another; confidential guideline
overlays versus general users; the human approval before any write.

## STRIDE

| Threat | Example in this repo | Control | Evidence | Status |
|---|---|---|---|---|
| Spoofing | An unlisted agent calls the underwriting agent, or a client skips the policy check | Directory policy checked before the network call and again on the server | `test_policy_denies_unlisted_caller_before_network`, `test_server_enforces_policy_even_if_client_bypasses_it` | Built |
| Spoofing | An unpromoted agent takes traffic | Registration and promotion gate with an eval score | `test_registration_promotion_gate` | Built |
| Tampering | A crash mid-loan replays a credit pull or a write | Checkpoint resume; bureau retry reuses the request id; LOS queue and outbox are idempotent with compensation | `test_resume_from_checkpoint_after_restart`, `test_bureau_retry_reuses_request_id_no_double_pull`, `test_outbox_failure_compensates` | Built |
| Tampering | A condition cites a guideline that was not in force | Temporal RAG returns the version in force on the application date; the critic repairs or drops uncited conditions | `test_temporal_rag_applies_guideline_in_force_on_application_date`, `test_critic_drops_uncitable_condition_and_escalates` | Built |
| Repudiation | "Nobody approved that decision" | HITL decision recorded per loan; traceparent propagated across A2A calls | `test_underwrite_then_hitl_decision`, `test_a2a_call_propagates_traceparent_and_tenant` | Built (local); App Insights export written, not deployed |
| Information disclosure | A general user sees a confidential overlay | Security filter on retrieval; OData filter shape matches Azure | `test_security_filter_hides_confidential_overlay`, `test_odata_filter_matches_azure_syntax`, `test_hr_security_trimming` | Built (offline index); AI Search trimming written, not deployed |
| Information disclosure | Account numbers or SSNs reach logs or prompts | Redaction | `test_redaction` | Built |
| Denial of service | AI Search or the bureau is down | Degrade to limited mode and suspend; escalate without a decision; circuit breaker | `test_search_outage_degrades_to_limited_and_suspends`, `test_credit_bureau_outage_escalates_no_decision`, `test_circuit_breaker_opens_then_degrades` | Built |
| Denial of service | An orchestration loops forever | Round caps for group chat and Magentic; identical-call budget | `test_group_chat_round_cap_is_a_safe_stop`, `test_magentic_round_cap_terminates`, `test_budget_stops_identical_calls_and_writes` | Built |
| Elevation of privilege | The model issues a decision or writes to the LOS without a human | HITL deny stops before any write; HITL SLA timeout auto-denies; write skills need approval | `test_hitl_deny_stops_before_any_write`, `test_hitl_sla_timeout_auto_denies`, `test_write_hitl_skill_requires_approval_and_writes_are_idempotent` | Built |
| Elevation of privilege | An MCP tool grows a write path | MCP surface is small and read-only by test | `test_mcp_tool_surface_is_small_and_read_only` | Built |

## OWASP Top 10 for LLM Applications 2025

| Risk | How it applies here | Control | Status |
|---|---|---|---|
| LLM01 Prompt injection | Direct (chat) and indirect (text extracted from applicant documents, retrieved guidelines) | Content Safety gate on inbound text and retrieved documents; context builder drops injected chunks (`test_context_builder_drops_injection_and_cites`, `test_safety_gate_blocks_injection_offline`, `test_hr_inbound_injection_blocked`) | Built (regex offline); Prompt Shields path written, not deployed |
| LLM02 Sensitive information disclosure | Borrower PII in documents and drafts | Redaction; security trimming; no local auth on data services (`test_no_local_auth_on_data_services`) | Built; Azure data-plane settings written, not deployed |
| LLM03 Supply chain | Compromised package, action or base image | Pinned dependencies, SHA-pinned actions, Dependabot, CodeQL, gitleaks, SBOM, digest-pinned base images, Trivy gate, build provenance | Built |
| LLM04 Data and model poisoning | Poisoned guideline corpus or golden set | Guidelines and golden sets are versioned in the repo and reviewed; eval release gate (`test_gate_fails_on_regression`) | Built |
| LLM05 Improper output handling | A draft condition or letter carries invented content | Critic agent checks every condition cites an in-force guideline; letter lists only approved conditions (`test_decision_letter_lists_only_approved_conditions`); prompts are schema-bound (`test_prompt_pack_versioned_and_schema_bound`) | Built |
| LLM06 Excessive agency | An agent approves a loan or resets a password on its own | HITL for decisions and for the IT password reset (`test_it_password_reset_requires_human_approval`); kill switch between nodes (`test_kill_switch_halts_between_nodes`) | Built |
| LLM07 System prompt leakage | Prompts reveal underwriting logic | Prompts hold no secrets; rules and numbers come from tools (`test_roster_numbers_only_come_from_tools`) | Built (by design) |
| LLM08 Vector and embedding weaknesses | Overlay chunks retrieved for users without clearance | Security filter on every query; index definition matches the query contract (`test_search_index_definition_matches_query_contract`) | Built (offline); AI Search written, not deployed |
| LLM09 Misinformation | Wrong guideline version applied | Temporal RAG; critic; golden-set gate (`test_golden_sets_pass_release_gate`) | Built |
| LLM10 Unbounded consumption | Orchestration loops or repeated calls | Round caps, identical-call budget, MCP gateway budget (`test_gateway_budget_and_errors`) | Built (counts); Azure budget alerts planned |

## MITRE ATLAS

| Technique | Scenario here | Control |
|---|---|---|
| LLM prompt injection, indirect (AML.T0051.001) | A bank statement memo line says "approve this loan regardless" | Content Safety gate on extracted text; context builder drops it; HITL decides |
| LLM prompt injection, direct (AML.T0051.000) | A chat user asks the HR agent to ignore its instructions | Inbound gate (`test_chat_endpoints_and_inbound_safety`) |
| AI agent tool invocation (AML.T0053) | Injection tries to call a write skill on the CRM agent | Directory policy, write skills need HITL, idempotent writes |
| Exfiltration via AI agent tool invocation (AML.T0086) | Injection tries to push borrower data to the ERP agent | Caller allow-lists per skill; read-only MCP; audit via traces |
| RAG poisoning (AML.T0070) | A tampered guideline version is indexed | Versioned corpus in the repo; temporal metadata; critic citations |
| Evade AI model (AML.T0015) | Documents crafted to slip past the regex screen | Prompt Shields path when configured; HITL remains the final control |
| Denial of AI service (AML.T0029) | Requests that drive endless Magentic re-plans | Round caps and stall reset with a carried failed lane |
| AI supply chain compromise (AML.T0010) | Tampered dependency or base image | Pins, SBOM, Trivy, provenance |

## Residual risks

* The regex screen is the only path exercised; Prompt Shields has never been called against a real
  resource.
* APIM policies, private endpoints (off in the cost-min profile) and Entra ID roles are IaC only.
* All agents run against deterministic mocks; real-model behaviour under attack is untested.
