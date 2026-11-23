# `skills/`: procedures supplied to the Copilot harness

Skills are the developer's part of a harness agent: reusable instructions the managed loop
can apply. Foundry would publish these with `azd ai skill create`. Here they are files the
offline harness reads.

| Path | What it holds |
|---|---|
| [`underwrite-file/`](underwrite-file/README.md) | Loan-commitment procedure used by the sample. |
