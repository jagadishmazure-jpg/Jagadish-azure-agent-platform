// azure-agent-platform — `azd up` entry point.
// Everything is parameterized; the default 'cost-min' profile picks the cheapest SKUs that still
// exercise every feature (scale-to-zero Container Apps, serverless Cosmos, Consumption APIM,
// Basic Service Bus, Basic Search with the free semantic-ranker plan, pay-per-call AI services).
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name; used for the resource group name and resource token.')
param environmentName string

@minLength(1)
@description('Primary region. Must offer the chosen models (GlobalStandard) and semantic ranker.')
param location string

@description('Object id of the deploying principal (azd sets AZURE_PRINCIPAL_ID).')
param principalId string = ''
@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@allowed(['cost-min', 'standard'])
param costProfile string = 'cost-min'

@description('Private endpoints + VNet-integrated Container Apps. Off by default (adds hourly PE + DNS cost; forces Service Bus Premium).')
param privateLink bool = false

@description('Action group, metric + log alert rules and diagnostic settings to Log Analytics. Cheap; on by default.')
param enableAlerts bool = true
@description('Optional on-call email for the action group. Empty = alerts fire in Azure Monitor only.')
param alertEmail string = ''
@description('Microsoft Defender for Cloud plans. SUBSCRIPTION-WIDE and billed per resource, so off by default.')
param enableDefender bool = false
param defenderPlans array = ['AI', 'Arm', 'CosmosDbs', 'KeyVaults']

@description('Deploy the Dynamics 365-style / Salesforce-style / SAP-style stand-in A2A agents.')
param deployVendorStandins bool = false

// ---- models (verified current defaults; override per region/quota) ----
param chatModelName string = 'gpt-5-mini'
param chatModelVersion string = '2025-08-07'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param chatDeploymentSku string = 'GlobalStandard'
param chatCapacity int = costProfile == 'cost-min' ? 10 : 50
param embeddingModelName string = 'text-embedding-3-small'
param embeddingModelVersion string = '1'
param embeddingCapacity int = costProfile == 'cost-min' ? 10 : 50

// ---- SKU overrides (empty = profile default) ----
@allowed(['', 'Consumption', 'Developer', 'BasicV2', 'StandardV2'])
param apimSku string = ''
@allowed(['', 'free', 'basic', 'standard'])
param searchSku string = ''
@allowed(['', 'Basic', 'Standard', 'Premium'])
param serviceBusSku string = ''
@allowed(['F0', 'S0'])
param docIntelSku string = 'S0'
@allowed(['F0', 'S0'])
param contentSafetySku string = 'S0'

param apimPublisherEmail string = 'noreply@example.com'
param entraTenantId string = ''
param entraAudience string = ''

var profiles = {
  'cost-min': { apim: 'Consumption', search: 'basic', serviceBus: 'Basic', minReplicas: 0, logQuotaGb: 1 }
  standard: { apim: 'Developer', search: 'standard', serviceBus: 'Standard', minReplicas: 1, logQuotaGb: -1 }
}
var p = profiles[costProfile]
var effectiveServiceBusSku = privateLink ? 'Premium' : (empty(serviceBusSku) ? p.serviceBus : serviceBusSku)
var effectiveSearchSku = empty(searchSku) ? p.search : searchSku
var effectiveApimSku = empty(apimSku) ? p.apim : apimSku
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName, workload: 'azure-agent-platform', costProfile: costProfile }
var publicAccess = privateLink ? 'Disabled' : 'Enabled'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module identity 'modules/identity.bicep' = {
  scope: rg
  name: 'identity'
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: { location: location, tags: tags, resourceToken: resourceToken, dailyQuotaGb: p.logQuotaGb }
}

module network 'modules/network.bicep' = if (privateLink) {
  scope: rg
  name: 'network'
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

module search 'modules/search.bicep' = {
  scope: rg
  name: 'search'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    sku: effectiveSearchSku
    publicNetworkAccess: toLower(publicAccess)
  }
}

module foundry 'modules/foundry.bicep' = {
  scope: rg
  name: 'foundry'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatDeploymentSku: chatDeploymentSku
    chatCapacity: chatCapacity
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    embeddingCapacity: embeddingCapacity
    searchEndpoint: search.outputs.endpoint
    searchResourceId: search.outputs.id
    publicNetworkAccess: publicAccess
  }
}

module docintel 'modules/cognitive.bicep' = {
  scope: rg
  name: 'docintel'
  params: {
    location: location
    tags: tags
    name: 'di-${resourceToken}'
    kind: 'FormRecognizer'
    sku: docIntelSku
    publicNetworkAccess: publicAccess
  }
}

module contentSafety 'modules/cognitive.bicep' = {
  scope: rg
  name: 'contentsafety'
  params: {
    location: location
    tags: tags
    name: 'cs-${resourceToken}'
    kind: 'ContentSafety'
    sku: contentSafetySku
    publicNetworkAccess: publicAccess
  }
}

module cosmos 'modules/cosmos.bicep' = {
  scope: rg
  name: 'cosmos'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    dataContributorPrincipalIds: empty(principalId)
      ? [identity.outputs.orchestratorPrincipalId]
      : [identity.outputs.orchestratorPrincipalId, principalId]
    publicNetworkAccess: publicAccess
  }
}

module serviceBus 'modules/servicebus.bicep' = {
  scope: rg
  name: 'servicebus'
  params: { location: location, tags: tags, resourceToken: resourceToken, sku: effectiveServiceBusSku }
}

module keyVault 'modules/keyvault.bicep' = {
  scope: rg
  name: 'keyvault'
  params: { location: location, tags: tags, resourceToken: resourceToken, publicNetworkAccess: publicAccess }
}

module registry 'modules/registry.bicep' = {
  scope: rg
  name: 'registry'
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

module roles 'modules/roles.bicep' = {
  scope: rg
  name: 'roles'
  params: {
    foundryAccountName: foundry.outputs.accountName
    searchName: search.outputs.name
    docIntelName: docintel.outputs.name
    contentSafetyName: contentSafety.outputs.name
    serviceBusName: serviceBus.outputs.name
    keyVaultName: keyVault.outputs.name
    registryName: registry.outputs.name
    orchestratorPrincipalId: identity.outputs.orchestratorPrincipalId
    toolsPrincipalId: identity.outputs.toolsPrincipalId
    foundryAccountPrincipalId: foundry.outputs.accountPrincipalId
    searchPrincipalId: search.outputs.principalId
    deployerPrincipalId: principalId
    deployerPrincipalType: principalType
  }
}

var peTargets = [
  { name: 'foundry', type: 'Microsoft.CognitiveServices/accounts', resource: 'aif-${resourceToken}', group: 'account', zones: ['cognitiveservices', 'openai', 'aiservices'] }
  { name: 'search', type: 'Microsoft.Search/searchServices', resource: 'srch-${resourceToken}', group: 'searchService', zones: ['search'] }
  { name: 'docintel', type: 'Microsoft.CognitiveServices/accounts', resource: 'di-${resourceToken}', group: 'account', zones: ['cognitiveservices'] }
  { name: 'contentsafety', type: 'Microsoft.CognitiveServices/accounts', resource: 'cs-${resourceToken}', group: 'account', zones: ['cognitiveservices'] }
  { name: 'cosmos', type: 'Microsoft.DocumentDB/databaseAccounts', resource: 'cosmos-${resourceToken}', group: 'Sql', zones: ['cosmos'] }
  { name: 'keyvault', type: 'Microsoft.KeyVault/vaults', resource: 'kv-${resourceToken}', group: 'vault', zones: ['keyvault'] }
  { name: 'servicebus', type: 'Microsoft.ServiceBus/namespaces', resource: 'sb-${resourceToken}', group: 'namespace', zones: ['servicebus'] }
]

module privateEndpoints 'modules/private-endpoint.bicep' = [for pe in (privateLink ? peTargets : []): {
  scope: rg
  name: 'pe-${pe.name}'
  params: {
    location: location
    tags: tags
    name: 'pe-${pe.name}-${resourceToken}'
    subnetId: network!.outputs.peSubnetId
    targetResourceId: resourceId(subscription().subscriptionId, rg.name, pe.type, pe.resource)
    groupId: pe.group
    dnsZoneIds: map(pe.zones, z => network!.outputs.zoneIds[z])
  }
  dependsOn: [foundry, search, docintel, contentSafety, cosmos, keyVault, serviceBus]
}]

module acaEnv 'modules/containerapps-env.bicep' = {
  scope: rg
  name: 'aca-env'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    logAnalyticsName: monitoring.outputs.logAnalyticsName
    infrastructureSubnetId: privateLink ? network!.outputs.acaSubnetId : ''
  }
}

// ---- application settings shared by the services ----
var commonEnv = [
  { name: 'AAP_MODE', value: 'azure' }
  { name: 'AAP_A2A_REMOTE', value: '1' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: monitoring.outputs.appInsightsConnectionString }
  { name: 'A2A_UNDERWRITING_AGENT_URL', value: 'http://ca-underwriting-agent' }
  { name: 'A2A_CRM_AGENT_URL', value: 'http://ca-crm-agent' }
  { name: 'A2A_ERP_AGENT_URL', value: 'http://ca-erp-agent' }
  { name: 'A2A_DYNAMICS_CRM_STANDIN_URL', value: 'http://ca-dynamics-crm-standin' }
  { name: 'A2A_SALESFORCE_CRM_STANDIN_URL', value: 'http://ca-salesforce-crm-standin' }
  { name: 'A2A_SAP_ERP_STANDIN_URL', value: 'http://ca-sap-erp-standin' }
  { name: 'MCP_CREDIT_BUREAU_URL', value: 'http://ca-mcp-credit-bureau/mcp' }
  { name: 'MCP_LOS_URL', value: 'http://ca-mcp-los/mcp' }
]
var orchestratorEnv = concat(commonEnv, [
  { name: 'AZURE_CLIENT_ID', value: identity.outputs.orchestratorClientId }
  { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundry.outputs.projectEndpoint }
  { name: 'FOUNDRY_MODEL', value: foundry.outputs.chatDeploymentName }
  { name: 'AZURE_OPENAI_ENDPOINT', value: foundry.outputs.openAiEndpoint }
  { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: foundry.outputs.embeddingDeploymentName }
  { name: 'AZURE_SEARCH_ENDPOINT', value: search.outputs.endpoint }
  { name: 'AZURE_DOCINTEL_ENDPOINT', value: docintel.outputs.endpoint }
  { name: 'AZURE_CONTENT_SAFETY_ENDPOINT', value: contentSafety.outputs.endpoint }
  { name: 'AZURE_COSMOS_ENDPOINT', value: cosmos.outputs.endpoint }
  { name: 'AZURE_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fqdn }
])
var toolsEnv = concat(commonEnv, [{ name: 'AZURE_CLIENT_ID', value: identity.outputs.toolsClientId }])

var coreApps = [
  { name: 'ca-bff', service: 'bff', external: true, orchestrator: true, command: [] }
  { name: 'ca-underwriting-agent', service: 'a2a-underwriting', external: false, orchestrator: true, command: ['python', '-m', 'agentplatform.a2a', 'underwriting-agent'] }
  { name: 'ca-crm-agent', service: 'a2a-crm', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.a2a', 'crm-agent'] }
  { name: 'ca-erp-agent', service: 'a2a-erp', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.a2a', 'erp-agent'] }
  { name: 'ca-mcp-credit-bureau', service: 'mcp-credit-bureau', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.mcp_servers', 'credit-bureau'] }
  { name: 'ca-mcp-los', service: 'mcp-los', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.mcp_servers', 'los'] }
]
var standinApps = [
  { name: 'ca-dynamics-crm-standin', service: 'a2a-dynamics-standin', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.a2a', 'dynamics-crm-standin'] }
  { name: 'ca-salesforce-crm-standin', service: 'a2a-salesforce-standin', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.a2a', 'salesforce-crm-standin'] }
  { name: 'ca-sap-erp-standin', service: 'a2a-sap-standin', external: false, orchestrator: false, command: ['python', '-m', 'agentplatform.a2a', 'sap-erp-standin'] }
]
var apps = deployVendorStandins ? concat(coreApps, standinApps) : coreApps

module containerApps 'modules/containerapp.bicep' = [for a in apps: {
  scope: rg
  name: a.name
  params: {
    location: location
    tags: tags
    name: a.name
    serviceName: a.service
    environmentId: acaEnv.outputs.id
    identityId: a.orchestrator ? identity.outputs.orchestratorId : identity.outputs.toolsId
    registryServer: registry.outputs.loginServer
    external: a.external
    command: a.command
    env: a.orchestrator ? orchestratorEnv : toolsEnv
    minReplicas: p.minReplicas
    healthPath: startsWith(a.service, 'mcp-') ? '' : '/healthz'
  }
  dependsOn: [roles] // AcrPull must exist before the first image pull
}]

module apim 'modules/apim.bicep' = {
  scope: rg
  name: 'apim'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    sku: effectiveApimSku
    publisherEmail: apimPublisherEmail
    bffUrl: containerApps[0].outputs.url
    entraTenantId: entraTenantId
    entraAudience: entraAudience
  }
}

// ---- alerting, diagnostics and Defender for Cloud (built offline; not deployed) ----
module alerts 'modules/alerts.bicep' = if (enableAlerts) {
  scope: rg
  name: 'alerts'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    actionGroupShortName: 'agentplat'
    alertEmail: alertEmail
    appInsightsId: monitoring.outputs.appInsightsId
    metricAlerts: [
      { name: 'sb-dead-letters', scope: serviceBus.outputs.id, namespace: 'Microsoft.ServiceBus/namespaces', metric: 'DeadletteredMessages', aggregation: 'Maximum', operator: 'GreaterThan', threshold: 0, severity: 2, description: 'Queued LOS writes or outbox messages are dead-lettering' }
      { name: 'kv-availability', scope: keyVault.outputs.id, namespace: 'Microsoft.KeyVault/vaults', metric: 'Availability', aggregation: 'Average', operator: 'LessThan', threshold: 99, severity: 1, description: 'Key Vault availability below 99%' }
      { name: 'foundry-5xx', scope: foundry.outputs.accountId, namespace: 'Microsoft.CognitiveServices/accounts', metric: 'ServerErrors', aggregation: 'Total', operator: 'GreaterThan', threshold: 5, severity: 2, description: 'Foundry model endpoint returning server errors' }
      { name: 'content-safety-5', scope: contentSafety.outputs.id, namespace: 'Microsoft.CognitiveServices/accounts', metric: 'ServerErrors', aggregation: 'Total', operator: 'GreaterThan', threshold: 5, severity: 2, description: 'Content Safety failing; Prompt Shields fail closed, so requests are being blocked' }
    ]
    logAlerts: [
      { name: 'failed-requests', query: 'requests | where success == false', threshold: 5, severity: 2, description: 'More than 5 failed requests in 15 minutes' }
      { name: 'exceptions', query: 'exceptions', threshold: 10, severity: 3, description: 'Exception spike in the services' }
      { name: 'dependency-fail', query: 'dependencies | where success == false', threshold: 10, severity: 3, description: 'Failing calls to models, MCP servers or A2A agents' }
    ]
  }
}

module diagnostics 'modules/diagnostics.bicep' = if (enableAlerts) {
  scope: rg
  name: 'diagnostics'
  params: {
    logAnalyticsId: monitoring.outputs.logAnalyticsId
    foundryAccountName: foundry.outputs.accountName
    searchName: search.outputs.name
    docIntelName: docintel.outputs.name
    contentSafetyName: contentSafety.outputs.name
    cosmosName: cosmos.outputs.name
    serviceBusName: serviceBus.outputs.name
    keyVaultName: keyVault.outputs.name
    registryName: registry.outputs.name
  }
}

module defender 'modules/defender.bicep' = if (enableDefender) {
  name: 'defender'
  params: { plans: defenderPlans }
}

// ---- outputs → azd env (consumed by hooks, scripts, and local AAP_MODE=azure runs) ----
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output FOUNDRY_MODEL string = foundry.outputs.chatDeploymentName
output AZURE_OPENAI_ENDPOINT string = foundry.outputs.openAiEndpoint
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = foundry.outputs.embeddingDeploymentName
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_SEARCH_CONNECTION string = foundry.outputs.searchConnectionName
output AZURE_DOCINTEL_ENDPOINT string = docintel.outputs.endpoint
output AZURE_CONTENT_SAFETY_ENDPOINT string = contentSafety.outputs.endpoint
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.endpoint
output AZURE_SERVICEBUS_NAMESPACE string = serviceBus.outputs.fqdn
output AZURE_KEY_VAULT_URI string = keyVault.outputs.uri
output APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output BFF_URL string = containerApps[0].outputs.url
output EVAL_MODEL_DEPLOYMENT string = foundry.outputs.chatDeploymentName
