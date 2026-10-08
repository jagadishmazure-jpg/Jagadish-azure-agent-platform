# Deploying with azd

> Nothing in this repo has been deployed. No Azure resources were created while building it. This page describes the intended path.

## Prerequisites

* Azure CLI and the [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/) (`azd`). Docker is **not** required, because images build remotely in ACR (`remoteBuild: true`).
* On the subscription: **Owner**, or **Contributor + Role Based Access Control Administrator**. The template creates role assignments.
* Model quota in the target region for `gpt-5-mini` (GlobalStandard) and `text-embedding-3-small`. Check it with `az cognitiveservices usage list -l <region>`. If the model or region isn't available, override `AAP_CHAT_MODEL`, `AAP_CHAT_MODEL_VERSION`, or `chatDeploymentSku`.
* Pick a region that offers semantic ranker (see the AI Search region support page).

## Up

```bash
azd auth login
azd env new aap-dev --location eastus2
azd env set AAP_COST_PROFILE cost-min          # default
azd env set AAP_APIM_PUBLISHER_EMAIL you@example.com
# optional: azd env set AAP_ENTRA_TENANT_ID <tid>; azd env set AAP_ENTRA_AUDIENCE api://agent-platform
azd up
```

`azd up` does three things:

1. **Provision:** `infra/main.bicep` at subscription scope creates `rg-<env>` and everything listed in `docs/cost-estimate.md`.
2. **Postprovision hook** (`scripts/postprovision.sh`):
   * seeds the `investor-guidelines` and `hr-policies` indexes with embeddings
   * registers `hr-policy-agent` and `it-servicedesk-agent` in Foundry Agent Service
   * checks that the agent cards are current
3. **Deploy:** builds the three Dockerfiles in ACR and rolls out the six Container Apps, matched by their `azd-service-name` tags.

Then:

```bash
azd env get-values > .env && set -a && . ./.env && set +a
export AAP_MODE=azure
python scripts/run_evals.py --azure                           # Groundedness/Relevance + custom evaluators, logged to the Foundry project
python scripts/foundry_register.py --invoke hr-policy-agent "How much parental leave do I get?"
curl -X POST "$APIM_GATEWAY_URL/agents/loans/L-1001/underwrite" -H "Ocp-Apim-Subscription-Key: <key>"
```

## Kill switches

* **Global:** in APIM, set the named value `agents-enabled` to `false`. Every call then returns 503.
* **Per agent:** `POST /directory/{agent}/kill` on the BFF (requires the `platform-admins` group). In this sample the directory state is per replica. Production would back it with Cosmos or App Configuration.

## CI/CD with GitHub Actions and OIDC (disabled by default)

The pipeline lives in [`deployment.md`](deployment.md): pull-request checks for the Terraform stack, a `deploy.yml` workflow that goes dev -> prod through GitHub Environments with required reviewers, a `deploy_tool` input (`bicep` or `terraform`), OIDC login with federated credentials (no secrets), smoke tests and a manual `teardown.yml`. Every deploy job is gated behind the repository variable `DEPLOY_ENABLED`, which is not set, so nothing runs against Azure. `azd up` below remains the laptop path.

## Private networking

Run `azd env set AAP_PRIVATE_LINK true`. This adds:

* a VNet, with Container Apps VNet-integrated
* private endpoints and private DNS zones for Foundry, Search, Document Intelligence, Content Safety, Cosmos, Key Vault, and Service Bus
* public network access disabled on those services
* Service Bus forced to Premium

* one NSG on both subnets (default rules; the same in Bicep and Terraform)

The postprovision hook then needs a runner that has network line-of-sight, such as a self-hosted runner in the VNet.

## Alerts, diagnostics and Defender for Cloud

Written and validated offline; never deployed.

* **On by default** (`AAP_ENABLE_ALERTS`, Bicep `enableAlerts`, Terraform `enable_alerts`): an action group, 4 metric alert rules (Service Bus dead letters, Key Vault availability, Foundry and Content Safety server errors), 3 KQL alert rules on Application Insights (failed requests, exceptions, failing dependencies) and diagnostic settings that send `allLogs` and `AllMetrics` from the 8 data and AI resources to Log Analytics. Set `azd env set AAP_ALERT_EMAIL oncall@example.com` to get email; without it the alerts only show in Azure Monitor. Diagnostic logs count against the Log Analytics daily cap in the `cost-min` profile.
* **Off by default** (`AAP_ENABLE_DEFENDER`, `enableDefender`, `enable_defender`): Defender for Cloud plans `AI`, `Arm`, `CosmosDbs` and `KeyVaults` at `Standard` tier. These apply to every resource of that type in the subscription and are billed per resource, so turn them on only in a subscription you own, and check the [Defender for Cloud pricing](https://azure.microsoft.com/pricing/details/defender-for-cloud/) first.

## Teardown

```bash
azd down --purge --force
```
