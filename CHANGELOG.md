# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no versioned releases, so entries are grouped by milestone, newest first.

## Unreleased

### Added

- Supply-chain hardening: every GitHub Action pinned to a commit SHA with a version comment, top-level `permissions` on every workflow, a gitleaks job in CI, a CodeQL workflow, `.github/dependabot.yml` and a guard test (`test_workflows_are_hardened`).
- GitHub settings: Dependabot alerts and security updates, private vulnerability reporting and a `main` ruleset (no force-push or deletion; CI required on pull requests).
- Component docs in `docs/components/` (17 standard sections each), `docs/implementation-guide.md`, `docs/adopt-this.md` and the `scripts/doc_drift.py` CI check that keeps pasted output and code excerpts in sync with the code.
- `CODEOWNERS` and a README in every folder.
- `docs/best-practices.md`: cloud and agentic AI practices with honest status and links.
- Architecture decision records in `docs/adr/`.
- `SECURITY.md`, `CONTRIBUTING.md` and this changelog.

### Changed

- README sections follow one order: what, why, architecture, run, test, deploy, limits.

## Milestone 2: delivery pipeline and orchestration patterns

### Added

- Terraform twin of the Bicep in `infra/terraform` (CAF names, tags, dev/prod tfvars, remote state, offline `terraform test`).
- GitHub Actions `infra.yml` (Terraform checks, tflint, checkov, image builds), `deploy.yml` (dev -> prod, Bicep or Terraform, OIDC, gated by `DEPLOY_ENABLED`) and `teardown.yml`.
- `docs/deployment.md`.
- All five MAF prebuilt orchestrations run on one loan review, with a generated comparison.
- Recruiter summary in the README.

### Changed

- The earlier `azd` deploy workflow (gated by `ENABLE_DEPLOY`) was replaced by the new pipeline.

## Milestone 1: platform and flagship workflow

### Added

- Harness (budgets, kill switch, resilience, five-exit failure table, OpenTelemetry), prompt pack, Content Safety gate.
- Temporal and ACL-aware retrieval, graph RAG, Document Intelligence extraction with fixtures.
- MCP servers behind a gateway; A2A agent cards, directory and kill switch; vendor stand-ins.
- Mortgage underwriting MAF graph with critic loop, HITL and checkpoints; HR and IT single agents; BFF.
- Evals and release gate; Bicep for `azd up`; Dockerfiles, local mesh; CI.
