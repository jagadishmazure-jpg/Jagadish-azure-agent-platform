# Five-exit failure table — mortgage underwriting graph

Generated from `agentplatform.harness.failure.FAILURE_TABLE` by `scripts/render_docs.py`; the graph,
the chaos tests in `tests/test_mortgage_workflow.py`, and this page read the same data.

| Node | Success | Retry | Compensate | Degrade | Escalate |
|---|---|---|---|---|---|
| **intake** | All documents extracted with field confidence >= 0.80; CRM profile fetched over A2A. | Document Intelligence 429/5xx: 3 attempts, jittered backoff, circuit breaker per endpoint. | n/a (read-only). | Low-confidence fields become a 'provide legible copy' condition instead of guessed values. | DI unavailable after retries: file suspended to processor queue with trace id. |
| **income** | Qualifying income computed from W-2 + paystub YTD with guideline citation. | Model endpoint 429: retry, then fallback deployment for the narrative only. | n/a (read-only). | Model down: deterministic calculator output + templated rationale (numbers never from the LLM). | Income docs contradictory (>10% variance) -> underwriter review condition. |
| **assets** | Funds to close + reserves verified; large deposits flagged with citation. | Transient DI/model errors retried. | n/a (read-only). | Missing statement page -> condition for complete statement. | Insufficient funds to close -> suspend, human decides. |
| **credit** | Tri-merge pulled via credit-bureau MCP server (read-only, idempotent request id). | Bureau timeout: 2 retries with the same request id (no duplicate hard pulls). | n/a (bureau pull is logged, not reversible; idempotency prevents a second pull). | Never: credit is required for a decision. | Bureau unavailable -> file suspended 'credit unavailable'; no decision issued. |
| **knowledge** | Temporal + ACL-filtered guideline passages and graph neighborhood packed with source map. | AI Search 503: retry with backoff. | n/a (read-only). | Search down: known-guideline cache for top conditions, answer marked LIMITED, decision disabled. | Index lag beyond SLA: page knowledge owner; underwriter sees 'guidelines stale' banner. |
| **critic** | Every condition cites an in-force guideline present in the evidence pack. | One repair pass: re-retrieve for uncited conditions. | n/a. | Uncited conditions are dropped from the letter and listed for the underwriter. | Second failure -> underwriter review with critic report (never burn more tokens arguing). |
| **underwriter_review** | Underwriter approves conditions; graph resumes from checkpoint. | n/a (human node). | n/a. | n/a. | Deny stores reason; SLA timeout resolves to 'suspend', never to silent approval. |
| **decision_letter** | Letter rendered; LOS/ERP updates queued on Service Bus with idempotency key. | Queue send retried. | Queue write fails after letter drafted -> letter voided, status reverted to 'in review'. | n/a (a letter is either correct or not issued). | Compensation performed -> ops alert with trace. |

Chaos drills covered by tests: model outage (fallback → deterministic draft), search outage (known-policy
cache, answer marked limited, evidence-dependent writes disabled), bureau outage (suspend, no decision),
bureau timeout retried with the same request id (no double hard pull), LOS write failure (compensating
`in_review` status), prompt injection in retrieved text (screened out), kill switch, HITL SLA expiry.
