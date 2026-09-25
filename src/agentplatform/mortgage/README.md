# `mortgage/`: the underwriting-conditions flagship

The flagship multi-agent system on Microsoft Agent Framework. For a loan file it extracts
documents, pulls credit over MCP, fetches the CRM profile over A2A, retrieves the guideline
versions in force on the application date (ACL-trimmed) plus related-party graph facts,
computes income, assets and DTI with deterministic calculators, drafts cited conditions, runs
a critic with at most one repair pass, and parks the run durably for an underwriter at a HITL
checkpoint. Only after approval does it draft the decision letter and queue LOS writes.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`agents.py`](agents.py) | `AgentSuite`: one MAF `Agent` per role with instructions from the prompt pack and structured output bound to the prompt's schema. Model failure falls back to the fallback deployment, then to a deterministic draft. |
| [`calculators.py`](calculators.py) | Deterministic underwriting math: `monthly_pi`, `qualifying_income`, `asset_position`, `dti`, `days_between`. The model never computes money. |
| [`critic.py`](critic.py) | `check()`: deterministic, fail-closed checks that every condition cites an in-force guideline from the evidence pack. |
| [`models.py`](models.py) | Checkpoint-safe workflow messages: `LoanRequest`, `UWState`, `UnderwriterReview` (the HITL request: evidence ids, conditions, critic report) and `UnderwriterDecision`. |
| [`rules.py`](rules.py) | `topics_for` and `evaluate()`: calculator output plus the packed guideline params become a recommendation and cited draft conditions. Never returns a denial. |
| [`service.py`](service.py) | `UnderwritingService` (`start`, `decide`, `resume` from the latest checkpoint, `expire_reviews` for the HITL SLA) and `make_checkpoint_storage()` (Cosmos on Azure, files offline). Used by the BFF and the A2A underwriting agent. |
| [`workflow.py`](workflow.py) | `build_workflow()` and the executors: `IntakeExecutor`, `IncomeExecutor`, `CreditExecutor`, `KnowledgeExecutor`, `JoinExecutor`, `AssetsExecutor`, `UnderwritingExecutor`, `CriticExecutor`, `RepairExecutor`, `UnderwriterReviewExecutor` (`request_info`), `DecisionLetterExecutor`. `Deps` holds non-checkpointed runtime dependencies. |
| [`data/`](data/README.md) | Synthetic LOS, credit bureau and CRM records. |

## Graph

```
intake ──┬─> income ──┐
         ├─> credit ──┼─> join ─> assets ─> underwriting ─> critic ─┬─> repair ─> critic (max 1)
         └─> knowledge┘                                             └─> underwriter_review (HITL)
                                                                          └─> decision_letter
```

Every executor checks the kill switch and step budget (`MAX_STEPS = 20`), runs inside the
five-exit wrapper and emits a span; state is checkpointed after every superstep.

## Human-in-the-loop

`UnderwriterReviewExecutor` calls `ctx.request_info(UnderwriterReview, UnderwriterDecision)`
and the run goes idle in the checkpoint store. `POST /runs/{run_id}/decision` resumes it (even
after a restart, via `resume()`). An unanswered review resolves after its SLA (24 hours unless
the review says otherwise) to a denial / return to processing, never to silent approval.

## Try it

```bash
python scripts/demo.py                           # L-1001, L-1002, L-1003 end to end
pytest tests/test_mortgage_workflow.py           # 17 tests incl. chaos drills
```
