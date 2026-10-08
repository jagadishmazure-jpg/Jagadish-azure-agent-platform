# `infra/terraform/modules`

Reusable modules called by the root stack. Each one mirrors a file in [`../../modules/`](../../modules/README.md) (the Bicep modules), keeps the same defaults, and takes `resource_group_name`, `location` and `tags` as inputs.

| File | What it does |
|---|---|
| [`alerts/`](alerts/README.md) | Azure Monitor action group, metric alert rules, KQL log alert rules on Application Insights and diagnostic settings to Log Analytics. |
| [`apim/`](apim/README.md) | API Management in front of the services: optional Entra ID JWT validation, spoofable-header stripping, rate limit, traceparent injection (and, in the agent platform, a kill-switch named value). |
| [`cognitive/`](cognitive/README.md) | Single-purpose Cognitive Services account (Document Intelligence or Content Safety), keyless, with a custom subdomain. |
| [`containerapp/`](containerapp/README.md) | One Container App (HTTP service or KEDA queue worker) on a user-assigned identity, pulling from ACR with that identity. The image is ignored after creation because the pipeline rolls images. |
| [`containerapps-env/`](containerapps-env/README.md) | Container Apps managed environment on the Consumption workload profile, logging to Log Analytics; optional VNet integration. |
| [`cosmos/`](cosmos/README.md) | Cosmos DB for NoSQL, serverless, local auth disabled; database, containers, and the built-in data-contributor role for the given principals. |
| [`defender/`](defender/README.md) | Opt-in Defender for Cloud plans (`Standard` tier), called only when `enable_defender = true`. |
| [`foundry/`](foundry/README.md) | Microsoft Foundry: AIServices account (keyless, project management on), a Foundry project and optional AI Search connection via `azapi`, and model deployments via `azurerm_cognitive_deployment`. |
| [`identity/`](identity/README.md) | User-assigned managed identities, one per key in a static map, so role assignments can be keyed before the principal ids exist. |
| [`keyvault/`](keyvault/README.md) | Key Vault in RBAC mode (no access policies), soft delete 7 days, purge protection as a variable, and `Key Vault Secrets User` for the given workload identities. |
| [`monitoring/`](monitoring/README.md) | Log Analytics workspace (PerGB2018, optional daily cap) and a workspace-based Application Insights component. |
| [`naming/`](naming/README.md) | CAF naming helper: `<type>-<workload>-<env>-<region>-<instance>` (for example `rg-agentplat-dev-eus2-001`), compressed forms for Key Vault (24 chars, region dropped), ACR and Storage (alphanumeric), and an optional suffix for globally unique names. No resources. |
| [`network/`](network/README.md) | Optional private networking: VNet, delegated Container Apps subnet, private-endpoint subnet, NSG, private DNS zones and VNet links. |
| [`private-endpoint/`](private-endpoint/README.md) | One private endpoint plus its private DNS zone group. |
| [`registry/`](registry/README.md) | Azure Container Registry with the admin user disabled; `AcrPull` for the workload identities. |
| [`search/`](search/README.md) | Azure AI Search with API keys disabled (Entra ID only), system-assigned identity and the free semantic-ranker plan. |
| [`servicebus/`](servicebus/README.md) | Service Bus namespace (SAS disabled, TLS 1.2), queues with dead-lettering, and sender / receiver roles. |
