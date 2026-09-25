# `context/`: the context builder

The runtime that decides which evidence tokens reach the model. Agents never call Search
directly: they ask the builder for topics or questions with a principal (tenant and groups),
a business as-of date, an optional graph anchor and tool facts. The builder retrieves, drops
anything outside the caller's ACL or not in force on that date, screens injected passages,
redacts PII, packs within a budget and returns a cited `ContextPack` with a source map and a
log of what was dropped and why.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring and exports. |
| [`builder.py`](builder.py) | `ContextBuilder.build(...)` and `build_from_cache(...)` (known-guideline cache used when Search is down; the pack is marked limited). `ContextPack` (`ids`, `guideline_ids`, `rule`, `source_map`, `render`, `merge`, `to_dict` / `from_dict` for checkpointing) and `EvidenceItem`. |
| [`sanitize.py`](sanitize.py) | `redact_pii` and `estimate_tokens` helpers. |

## Design notes

- ACL and temporal validity are applied in the Search filter (see
  [`knowledge/search.py`](../knowledge/search.py)) and re-checked here, so the model never sees
  a passage the caller is not entitled to or that was not in force.
- The pack is JSON-serialisable so it can live in MAF checkpoints and be replayed after a restart.

Tests: `pytest tests/test_knowledge.py -k context_builder`.
