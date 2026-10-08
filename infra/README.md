# `infra/`: Bicep for `azd up`

Infrastructure as code for the whole platform, consumed by `azd` through
[`azure.yaml`](../azure.yaml). `main.bicep` is subscription-scoped: it creates the resource
group and composes the modules in [`modules/`](modules/README.md). Everything is parameterised;
the default `cost-min` profile picks the cheapest SKUs that still exercise every feature, and
`privateLink=true` switches data services to private endpoints.

| File | What it does |
|---|---|
| [`main.bicep`](main.bicep) | Entry point. Parameters include `environmentName`, `location`, `principalId`, `costProfile` (`cost-min` | `standard`), `privateLink`, `enableAlerts`, `alertEmail`, `enableDefender`, `deployVendorStandins`, model names/versions/capacity and optional SKU overrides. Composes identity, monitoring, optional network, AI Search, Foundry, Document Intelligence, Content Safety, Cosmos DB, Service Bus, Key Vault, ACR, RBAC, private endpoints, the Container Apps environment, one Container App per service and APIM, plus alert rules and diagnostic settings (on by default) and opt-in Defender for Cloud plans. Outputs the env vars the app reads (`FOUNDRY_PROJECT_ENDPOINT`, `AZURE_SEARCH_ENDPOINT`, `AZURE_COSMOS_ENDPOINT`, `BFF_URL`, ...). |
| [`main.parameters.json`](main.parameters.json) | azd parameter file: maps azd environment values (`${AZURE_ENV_NAME}`, `${AZURE_LOCATION}`, `${AZURE_PRINCIPAL_ID}`) and optional `AAP_*` overrides with defaults (`AAP_COST_PROFILE=cost-min`, `AAP_PRIVATE_LINK=false`, `AAP_DEPLOY_STANDINS=false`, chat model, APIM publisher, Entra tenant/audience) to Bicep parameters. |
| [`modules/`](modules/README.md) | One Bicep module per resource type. |
| [`terraform/`](terraform/README.md) | The same infrastructure in Terraform (`azurerm` + `azapi`), with CAF names, dev/prod tfvars, a partial remote-state backend and offline plan tests. Read its README for when to pick which tool. |

## Profiles

| | `cost-min` (default) | `standard` |
|---|---|---|
| APIM | Consumption | Developer |
| AI Search | basic | standard |
| Service Bus | Basic (Premium when `privateLink`) | Standard (Premium when `privateLink`) |
| Container Apps min replicas | 0 (scale to zero) | 1 |
| Log Analytics daily cap | 1 GB | none |

(Values from the `profiles` variable in `main.bicep`.) Billing dimensions are described in
[`docs/cost-estimate.md`](../docs/cost-estimate.md).

## Validate

```bash
az bicep build --file infra/main.bicep --stdout > /dev/null   # make bicep; CI runs the same build
pytest tests/test_infra.py                                    # static checks, no Azure calls
azd up                                                        # provision + deploy (not yet run)
```

`tests/test_infra.py` checks that `azure.yaml` services match Container App tags, that
`cost-min` is the default with Private Link off, that data services disable local auth, and
that the Bicep builds cleanly.

> **Status:** nothing in this repo has been deployed to Azure yet. The Azure code paths follow verified SDK signatures but have only run offline; see the root README's *Honest limitations*.
