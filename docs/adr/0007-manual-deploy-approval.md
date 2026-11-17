# ADR 0007: Deploy on a manual run with environment approval

- **Status:** Accepted
- **Supersedes:** [ADR 0005](0005-deploy-gated-off.md)

## Context

ADR 0005 kept `deploy.yml` from running by skipping every job unless the repository variable
`DEPLOY_ENABLED` was true, and the workflow also triggered on push to `main`. That showed a
pipeline existed, but a reviewer could not tell that the path was armed. A push-triggered
deploy would also try to create resources on every merge once the variable was set.

There is still no Azure subscription in this portfolio. The workflow has to be ready to run,
and it has to be impossible to start by accident.

## Decision

`deploy.yml` runs only on `workflow_dispatch`. The operator types `deploy` in the `confirm`
input. `dev` and `prod` are GitHub Environments: configure required reviewers on both before
the first run, so the run waits for approval. Prod is skipped unless `promote_to_prod` is set.
Azure login stays OIDC (`id-token: write`, `azure/login`, federated credentials). No client
secret is stored. Preflight fails if `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` or
`AZURE_SUBSCRIPTION_ID` is empty, before any image build.

`teardown.yml` stays manual, still requires the environment name to be typed again, and uses
the same OIDC login. The `DEPLOY_ENABLED` variable is no longer consulted.

`azd up` remains the laptop path. Both paths target the same Bicep (or, in the workflow, Bicep
or Terraform).

## Consequences

- A push to `main` no longer starts a deploy run.
- The first real run still needs the one-time setup in [docs/deployment.md](../deployment.md):
  federated credentials, GitHub Environments with reviewers, and the Actions variables.
- Without those, a manual run stops in preflight and does not call Azure.
- The pipeline itself has not been executed against a subscription.
