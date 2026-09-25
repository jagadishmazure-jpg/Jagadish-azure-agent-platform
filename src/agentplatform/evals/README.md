# `evals/`: golden sets, evaluators and release gate

The loop/ops layer. The runner executes the real targets (the mortgage workflow and the HR
agent) on the golden sets, writes rows with azure-ai-evaluation column names (`query`,
`response`, `context`, `ground_truth`) and scores them. Offline, only deterministic custom
evaluators run; with `--azure`, the same rows are also scored by azure-ai-evaluation's
Groundedness and Relevance evaluators and logged to the Foundry project (not yet run).

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`evaluators.py`](evaluators.py) | Custom evaluators with the azure-ai-evaluation call convention (keyword args in, dict out): `PolicyComplianceEvaluator` (every condition cites a guideline that exists and was in force), `ConditionRecallEvaluator` (required conditions present, forbidden ones absent), `CitationEvaluator` (HR citations and key fact). `call()` invokes an evaluator with only the columns its signature declares. |
| [`runner.py`](runner.py) | `load_golden`, `mortgage_rows`, `hr_rows`, `score_offline`, `score_azure` and `EvalReport`. `THRESHOLDS` is the release gate: policy_compliance 1.0, condition_recall 0.95, condition_leak 0.0 (max), recommendation_match 1.0, citation_exact 0.8, answer_contains 0.8. |
| [`golden/`](golden/README.md) | Golden JSONL sets for mortgage conditions and HR policy. |

## Run

```bash
python scripts/run_evals.py --out evals-out     # offline gate; exit 1 on regression (make evals / CI)
pytest tests/test_evals.py                      # gate, regression detection, evaluate() compatibility
```
