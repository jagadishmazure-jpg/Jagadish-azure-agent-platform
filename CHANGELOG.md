# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no versioned releases, so entries are grouped by date.

## Unreleased

### Added

- `docs/best-practices.md`: cloud and agentic AI practices with honest status and links.
- Architecture decision records in `docs/adr/`.
- `SECURITY.md`, `CONTRIBUTING.md` and this changelog.

### Changed

- README sections follow one order: what, why, architecture, run, test, deploy, limits.

## 2026-09-29

### Added

- Terraform twin of the Bicep in `infra/terraform` (CAF names, tags, dev/prod tfvars, remote state, offline `terraform test`).
- GitHub Actions `infra.yml` (Terraform checks, tflint, checkov, image builds), `deploy.yml` (dev -> prod, Bicep or Terraform, OIDC, gated by `DEPLOY_ENABLED`) and `teardown.yml`.
- `docs/deployment.md`.
- All five MAF prebuilt orchestrations run on one loan review, with a generated comparison.
- Recruiter summary in the README.

### Changed

- The earlier `azd` deploy workflow (gated by `ENABLE_DEPLOY`) was replaced by the new pipeline.

## 2026-09-25

### Added

- Harness (budgets, kill switch, resilience, five-exit failure table, OpenTelemetry), prompt pack, Content Safety gate.
- Temporal and ACL-aware retrieval, graph RAG, Document Intelligence extraction with fixtures.
- MCP servers behind a gateway; A2A agent cards, directory and kill switch; vendor stand-ins.
- Mortgage underwriting MAF graph with critic loop, HITL and checkpoints; HR and IT single agents; BFF.
- Evals and release gate; Bicep for `azd up`; Dockerfiles, local mesh; CI.
