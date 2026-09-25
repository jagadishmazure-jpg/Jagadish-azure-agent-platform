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

## CI/CD with OIDC (disabled by default)

`.github/workflows/deploy.yml` runs only on `workflow_dispatch`, and only when the repository variable `ENABLE_DEPLOY` is `true`. To set it up:

1. Create an app registration (or a user-assigned MI) with a **federated credential** for subject `repo:jagadishmazure-jpg/azure-agent-platform:environment:dev`.
2. Grant it Contributor, plus RBAC Administrator constrained to the roles in `infra/modules/roles.bicep`, on the subscription.
3. Add the repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, and `ENABLE_DEPLOY=true`. No secrets are stored.
4. Run the workflow. Its `teardown` input runs `azd down --purge`.

## Private networking

Run `azd env set AAP_PRIVATE_LINK true`. This adds:

* a VNet, with Container Apps VNet-integrated
* private endpoints and private DNS zones for Foundry, Search, Document Intelligence, Content Safety, Cosmos, Key Vault, and Service Bus
* public network access disabled on those services
* Service Bus forced to Premium

The postprovision hook then needs a runner that has network line-of-sight, such as a self-hosted runner in the VNet.

## Teardown

```bash
azd down --purge --force
```
