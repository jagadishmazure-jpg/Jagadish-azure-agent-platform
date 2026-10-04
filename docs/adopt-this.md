# Adopt this

How another team can reuse the platform: what to take, what to configure, and how to extend it without losing the controls. Every component page in [components/](components/README.md) ends with its own "Adopt this" steps; this page is the overview.

## What you can take

| If you need | Take | Start from |
|---|---|---|
| a durable multi-agent review with a human decision | `mortgage/` shape: intake, parallel evidence, join, deterministic rules, critic, human review, actions | [mortgage-workflow.md](components/mortgage-workflow.md) |
| to choose an orchestration pattern | `orchestrations/` and its `--compare` table | [orchestrations.md](components/orchestrations.md) |
| controlled calls between team-owned agents | `a2a/` catalog, directory, client, server | [a2a-control-plane.md](components/a2a-control-plane.md) |
| safe access to systems of record | `mcp_servers/` and `ToolGateway` | [mcp-tool-plane.md](components/mcp-tool-plane.md) |
| retrieval that respects dates and permissions | `knowledge/` and `context/` | [knowledge-and-context.md](components/knowledge-and-context.md) |
| budgets, kill switches and named failure exits | `harness/` | [harness.md](components/harness.md) |
| a quality gate in CI | `evals/` and `scripts/run_evals.py` | [evals.md](components/evals.md) |
| a landing zone | `infra/` (Bicep or Terraform) | [infrastructure.md](components/infrastructure.md) |

## Configure

1. Copy the repository or the packages you need; keep `config.py` as the only place that reads the environment.
2. Replace the synthetic data (`mortgage/data/`, `knowledge/data/`, `evals/golden/`) with your own, keeping the same shapes so the tests still run offline.
3. Rewrite the prompts in `prompts/pack/` and bump their versions.
4. Edit `a2a/catalog.py` with your agents, owners and allowed callers, then run `python scripts/export_agent_cards.py` and commit the cards.
5. Set `THRESHOLDS` in `evals/runner.py` to the levels your reviewers accept.
6. For Azure, edit `infra/main.parameters.json`, run `azd up` in a sandbox and set `AAP_MODE=azure`.

## Extend

- **New tool:** add it to an MCP server with an idempotency key for any write, call it through `ToolGateway`, add a test like `tests/test_mcp.py::test_los_queue_is_idempotent`.
- **New agent:** add a prompt and schema, build it with `get_chat_client()`, register it in the catalog; production registration needs an eval score of at least 0.85.
- **New node in the graph:** wrap it with `run_with_exits`, add its rows to `FAILURE_TABLE`, run `python scripts/render_docs.py`.
- **New docs output:** add an `<!-- output: cmd -->` or `<!-- code: path::name -->` block and run `python scripts/doc_drift.py`.

## Keep these invariants

- Models never compute money; calculators do.
- Every condition cites an in-force guideline, or the critic fails the run.
- No system-of-record write before a named human approves.
- Filters for dates and permissions run in the search query, not in the prompt.
- CI stays green on lint, tests, evals, agent-card drift, doc drift and the Bicep build.

## Ownership

`.github/CODEOWNERS` assigns the repository to @jagadishmazure-jpg. A team adopting this should replace that with its own owners per folder (for example `control-plane/` owned by the platform team, `src/agentplatform/mortgage/` by the domain team).
