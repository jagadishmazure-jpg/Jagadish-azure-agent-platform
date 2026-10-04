# Cost estimate: resources, SKUs, billing model

**This page has no dollar figures on purpose.** Prices vary by region, currency, agreement, and month. Use the official pricing pages linked below, or the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/), with the SKUs listed here. What this page does give you, for each resource, is the billing dimension and whether you pay while it sits idle.

Default profile: **`cost-min`** (`costProfile` parameter in `infra/main.bicep`). The `standard` profile shows what changes for a shared dev/test environment.

| # | Resource (Bicep module) | cost-min SKU | standard SKU | Billing dimension | Idle cost? | Pricing page |
|---|---|---|---|---|---|---|
| 1 | Foundry account (`AIServices`) + project (`foundry.bicep`) | S0 | S0 | The account and project have no standing fee. You pay for what you call. | No | [Foundry](https://azure.microsoft.com/pricing/details/ai-foundry/) |
| 2 | Chat deployment `gpt-5-mini` (`2025-08-07`) | GlobalStandard, 10K TPM cap | GlobalStandard, 50K TPM | Per 1M input / cached input / output tokens. Capacity is a rate limit, not a reservation. | No | [Azure OpenAI in Foundry Models](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/) |
| 3 | Embedding deployment `text-embedding-3-small` v1 | Standard, 10K TPM | Standard, 50K TPM | Per 1M tokens | No | same as above |
| 4 | Azure AI Search (`search.bicep`) | **Basic**, 1 replica, 1 partition, semantic ranker on the **free** plan | Standard S1 | **Per search-unit-hour** while provisioned. Semantic ranker is a separate per-1K-request charge once past the free monthly allowance, and only if you switch to the `standard` plan. | **Yes (hourly)**. The largest fixed cost in cost-min. `searchSku=free` avoids it, but Free has limits (one per subscription, no private endpoint, may be reclaimed when inactive). | [AI Search](https://azure.microsoft.com/pricing/details/search/) |
| 5 | Document Intelligence (`cognitive.bicep`, kind FormRecognizer) | S0 | S0 | Per page analyzed. Prebuilt models (pay stub, W-2, bank statement) are priced per page tier. | No | [Document Intelligence](https://azure.microsoft.com/pricing/details/ai-document-intelligence/) |
| 6 | Content Safety (`cognitive.bicep`, kind ContentSafety) | S0 | S0 | Per text record (a fixed character block) for text analysis and Prompt Shields | No | [Content Safety](https://azure.microsoft.com/pricing/details/cognitive-services/content-safety/) |
| 7 | Container Apps environment + 6 apps (`containerapps-env.bicep`, `containerapp.bicep`) | Consumption profile, **minReplicas 0**, 0.5 vCPU / 1 GiB | minReplicas 1 | Per vCPU-second, GiB-second, and requests, with a monthly free grant per subscription. Idle replicas bill at a reduced rate. Scaled-to-zero apps bill nothing. | No at 0 replicas. Yes with minReplicas ≥ 1. | [Container Apps](https://azure.microsoft.com/pricing/details/container-apps/) |
| 8 | API Management (`apim.bicep`) | **Consumption** | Developer (no SLA) | Consumption: per 10K calls after a monthly free grant. Developer/BasicV2/StandardV2: **per unit-hour**. | Consumption: no. Developer: **yes (hourly)**. | [API Management](https://azure.microsoft.com/pricing/details/api-management/) |
| 9 | Cosmos DB for NoSQL (`cosmos.bicep`) | **Serverless** | Serverless | Per million request units consumed, plus GB stored | Storage only | [Cosmos DB](https://azure.microsoft.com/pricing/details/cosmos-db/serverless/) |
| 10 | Service Bus (`servicebus.bicep`) | **Basic** (queues only) | Standard | Basic: per million operations. Standard: base charge per hour plus operations. Premium: per messaging unit-hour. | Basic: no. Standard/Premium: **yes**. | [Service Bus](https://azure.microsoft.com/pricing/details/service-bus/) |
| 11 | Key Vault (`keyvault.bicep`) | Standard | Standard | Per 10K operations | No | [Key Vault](https://azure.microsoft.com/pricing/details/key-vault/) |
| 12 | Container Registry (`registry.bicep`) | Basic | Basic | **Per registry-day** plus storage and build minutes (azd `remoteBuild`) | **Yes (daily)** | [Container Registry](https://azure.microsoft.com/pricing/details/container-registry/) |
| 13 | Log Analytics + workspace-based Application Insights (`monitoring.bicep`) | PerGB2018, 30-day retention, **1 GB/day cap** | no cap | Per GB ingested. Retention beyond the included period is per GB-month. | Only what you ingest | [Azure Monitor](https://azure.microsoft.com/pricing/details/monitor/) |
| 14 | User-assigned managed identities ×2, role assignments | – | – | Free | No | – |
| 15 | *(privateLink=true only)* VNet, 7 private endpoints, 7 private DNS zones | off | off | Private endpoints: **per endpoint-hour** plus per GB processed. DNS zones: per zone-month plus queries. This setting **forces Service Bus Premium**, which is hourly. | **Yes** | [Private Link](https://azure.microsoft.com/pricing/details/private-link/), [DNS](https://azure.microsoft.com/pricing/details/dns/) |

### Summary: what bills while nothing is running (cost-min)

* **Hourly or daily:** AI Search Basic and ACR Basic. That's the whole list.
* **Pay-per-use only:** model tokens, Document Intelligence pages, Content Safety records, Container Apps (scaled to zero), APIM Consumption calls, Cosmos serverless RUs, Service Bus Basic operations, Key Vault operations, Log Analytics GB.
* **Biggest levers:** `searchSku=free` (with the limits above), fewer eval runs (AI-assisted evaluators spend chat tokens), and the Log Analytics daily cap.

### Teardown

```bash
azd down --purge --force   # deletes the resource group; --purge also purges soft-deleted Key Vault + Cognitive Services accounts
```

* Key Vault purge protection is **off** by default (`enablePurgeProtection=false`), so `--purge` really does remove it. Turn it on for production.
* A soft-deleted Cognitive Services / Foundry account keeps its custom subdomain reserved until purged. `--purge` takes care of that.
* Afterwards, confirm nothing is left: `az group list --query "[?tags.\"azd-env-name\"=='<env>']"`, and `az cognitiveservices account list-deleted`.
