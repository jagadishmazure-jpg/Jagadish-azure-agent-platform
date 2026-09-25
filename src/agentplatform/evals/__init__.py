"""Loop/ops layer: golden sets, custom evaluators, and a gated eval runner.

Offline: deterministic custom evaluators only (policy compliance, citation recall, recommendation match).
Azure: the same rows are scored with azure-ai-evaluation (GroundednessEvaluator, RelevanceEvaluator
+ the custom evaluators) via `evaluate(...)`, logged to the Foundry project."""
