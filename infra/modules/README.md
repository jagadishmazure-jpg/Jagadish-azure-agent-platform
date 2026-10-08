# `infra/modules/`: Bicep modules

Single-purpose Bicep modules composed by [`../main.bicep`](../main.bicep). Each takes
`location` and `tags` plus its own parameters, uses Entra ID / managed identity instead of keys
where the service supports it, and exposes the endpoints and names that `main.bicep` turns into
azd outputs. `tests/test_infra.py` reads every `*.bicep` file here for static checks.

| File | What it does |
|---|---|
| [`alerts.bicep`](alerts.bicep) | Azure Monitor action group (optional on-call email), metric alert rules and KQL log alert rules on Application Insights. |
| [`apim.bicep`](apim.bicep) | API Management as the gateway in front of the BFF (and optionally A2A agents): Entra ID JWT validation, identity headers derived from claims, rate limiting and a kill switch driven by a named value. |
| [`cognitive.bicep`](cognitive.bicep) | One Cognitive Services account, used twice: Document Intelligence (`FormRecognizer`) and Content Safety. |
| [`containerapp.bicep`](containerapp.bicep) | One Container App (BFF, MCP server or A2A agent) with a user-assigned identity and registry pull; azd replaces the placeholder image on deploy. |
| [`containerapps-env.bicep`](containerapps-env.bicep) | Container Apps managed environment on the Consumption plan (scale to zero), with optional VNet integration. |
| [`cosmos.bicep`](cosmos.bicep) | Cosmos DB for NoSQL, serverless: containers for MAF workflow checkpoints (partition key `/workflow_name`), agent memory and a run index (`/tenant_id`). |
| [`defender.bicep`](defender.bicep) | Opt-in Defender for Cloud plans at subscription scope (`enableDefender`, off by default: subscription-wide and billed). |
| [`diagnostics.bicep`](diagnostics.bicep) | Diagnostic settings sending `allLogs` and `AllMetrics` from the 8 data and AI resources to Log Analytics. |
| [`foundry.bicep`](foundry.bicep) | Microsoft Foundry: AIServices account with project management, one project, chat and embedding model deployments, and a project connection to AI Search using Entra ID. |
| [`identity.bicep`](identity.bicep) | Two user-assigned managed identities so blast radius follows the plane: `orchestrator` (BFF + underwriting agent) and `tools` (MCP servers and CRM/ERP/stand-in agents). |
| [`keyvault.bicep`](keyvault.bicep) | Key Vault in RBAC mode; purge protection off by default so `azd down --purge` fully cleans up a demo. |
| [`monitoring.bicep`](monitoring.bicep) | Log Analytics workspace (with optional daily cap) and workspace-based Application Insights as the OpenTelemetry sink. |
| [`network.bicep`](network.bicep) | Optional private networking: VNet with a Container Apps subnet and a private-endpoint subnet, one NSG on both, plus linked private DNS zones. |
| [`private-endpoint.bicep`](private-endpoint.bicep) | Generic private endpoint with DNS zone group for a target resource and group id. |
| [`registry.bicep`](registry.bicep) | Azure Container Registry for azd-built images; admin user disabled, pulls via managed identity. |
| [`roles.bicep`](roles.bicep) | Least-privilege RBAC assignments for the two identities and the deployer (built-in role ids). |
| [`search.bicep`](search.bicep) | Azure AI Search with semantic ranker; Entra ID only (local keys disabled). |
| [`servicebus.bicep`](servicebus.bicep) | Service Bus namespace with two queues, `los-writes` and `agent-outbox`, for queued writes (outbox pattern). |

Build check: `az bicep build --file infra/main.bicep --stdout > /dev/null` (compiles every
module referenced from `main.bicep`).

> **Status:** nothing in this repo has been deployed to Azure yet. The Azure code paths follow verified SDK signatures but have only run offline; see the root README's *Honest limitations*.
