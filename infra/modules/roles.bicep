// Least-privilege RBAC. Built-in role IDs verified against the Azure built-in roles reference
// ("Azure AI User" is now displayed as "Foundry User"; same GUID).
param foundryAccountName string
param searchName string
param docIntelName string
param contentSafetyName string
param serviceBusName string
param keyVaultName string
param registryName string
param orchestratorPrincipalId string
param toolsPrincipalId string
param foundryAccountPrincipalId string
param searchPrincipalId string
@description('Deployer (azd principal) — used by postprovision hooks to seed indexes and register agents.')
param deployerPrincipalId string = ''
@allowed(['User', 'ServicePrincipal'])
param deployerPrincipalType string = 'User'

var role = {
  foundryUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  serviceBusSender: '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: foundryAccountName }
resource search 'Microsoft.Search/searchServices@2023-11-01' existing = { name: searchName }
resource docintel 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: docIntelName }
resource safety 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: contentSafetyName }
resource sb 'Microsoft.ServiceBus/namespaces@2024-01-01' existing = { name: serviceBusName }
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: keyVaultName }
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = { name: registryName }

func ra(scopeId string, principalId string, roleId string) string => guid(scopeId, principalId, roleId)

// ---- orchestrator (BFF + underwriting agent) ----
resource o1 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: ra(foundry.id, orchestratorPrincipalId, role.foundryUser)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.foundryUser) }
}
resource o2 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: ra(foundry.id, orchestratorPrincipalId, role.openAiUser)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.openAiUser) }
}
resource o3 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: ra(search.id, orchestratorPrincipalId, role.searchIndexDataReader)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.searchIndexDataReader) }
}
resource o4 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: docintel
  name: ra(docintel.id, orchestratorPrincipalId, role.cognitiveServicesUser)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.cognitiveServicesUser) }
}
resource o5 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: safety
  name: ra(safety.id, orchestratorPrincipalId, role.cognitiveServicesUser)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.cognitiveServicesUser) }
}
resource o6 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: sb
  name: ra(sb.id, orchestratorPrincipalId, role.serviceBusSender)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.serviceBusSender) }
}
resource o7 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: ra(kv.id, orchestratorPrincipalId, role.keyVaultSecretsUser)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.keyVaultSecretsUser) }
}
resource o8 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: ra(acr.id, orchestratorPrincipalId, role.acrPull)
  properties: { principalId: orchestratorPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.acrPull) }
}

// ---- tools (MCP servers + CRM/ERP/stand-in agents): pull images + read secrets only ----
resource t1 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: ra(acr.id, toolsPrincipalId, role.acrPull)
  properties: { principalId: toolsPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.acrPull) }
}
resource t2 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: ra(kv.id, toolsPrincipalId, role.keyVaultSecretsUser)
  properties: { principalId: toolsPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.keyVaultSecretsUser) }
}

// ---- service-to-service: Foundry agents' AzureAISearchTool + Search integrated vectorizer ----
resource s1 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: ra(search.id, foundryAccountPrincipalId, role.searchIndexDataReader)
  properties: { principalId: foundryAccountPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.searchIndexDataReader) }
}
resource s2 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: ra(foundry.id, searchPrincipalId, role.openAiUser)
  properties: { principalId: searchPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.openAiUser) }
}

// ---- deployer (seed indexes, register agents, run evals) ----
resource d1 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: search
  name: ra(search.id, deployerPrincipalId, role.searchServiceContributor)
  properties: { principalId: deployerPrincipalId, principalType: deployerPrincipalType, roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.searchServiceContributor) }
}
resource d2 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: search
  name: ra(search.id, deployerPrincipalId, role.searchIndexDataContributor)
  properties: { principalId: deployerPrincipalId, principalType: deployerPrincipalType, roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.searchIndexDataContributor) }
}
resource d3 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: foundry
  name: ra(foundry.id, deployerPrincipalId, role.foundryUser)
  properties: { principalId: deployerPrincipalId, principalType: deployerPrincipalType, roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.foundryUser) }
}
resource d4 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: foundry
  name: ra(foundry.id, deployerPrincipalId, role.openAiUser)
  properties: { principalId: deployerPrincipalId, principalType: deployerPrincipalType, roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.openAiUser) }
}
