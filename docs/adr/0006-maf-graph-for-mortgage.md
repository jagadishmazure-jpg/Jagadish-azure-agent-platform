# ADR 0006: Use a MAF graph for mortgage, single agents elsewhere

- **Status:** Accepted

## Context

Not every use case needs multi-agent orchestration. HR policy questions need one retrieval tool; IT password resets need one approval-gated tool. Mortgage underwriting needs parallel evidence gathering, a critic loop, a durable human approval and compensating writes.

## Decision

HR and IT are single Microsoft Agent Framework agents (also registered as Foundry prompt agents). Mortgage is a MAF graph workflow with checkpoints. The five prebuilt MAF orchestrations are run on the same loan review and compared, so the choice is backed by measurements.

## Consequences

- Simple cases stay cheap and easy to reason about.
- The graph adds checkpoints, HITL and compensation where they pay for themselves.
- The comparison in `docs/orchestration-patterns.md` is generated from runs against the mock model, so it compares control flow and call counts, not model quality.
