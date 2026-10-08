// Diagnostic settings: allLogs + AllMetrics from every data and AI resource to Log Analytics.
// Mirrors the diagnostic_targets in infra/terraform/main.tf (module "alerts"). Not deployed.
param logAnalyticsId string
param foundryAccountName string
param searchName string
param docIntelName string
param contentSafetyName string
param cosmosName string
param serviceBusName string
param keyVaultName string
param registryName string

var settings = {
  workspaceId: logAnalyticsId
  logs: [{ categoryGroup: 'allLogs', enabled: true }]
  metrics: [{ category: 'AllMetrics', enabled: true }]
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: foundryAccountName }
resource search 'Microsoft.Search/searchServices@2023-11-01' existing = { name: searchName }
resource docintel 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: docIntelName }
resource contentSafety 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: contentSafetyName }
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = { name: cosmosName }
resource bus 'Microsoft.ServiceBus/namespaces@2024-01-01' existing = { name: serviceBusName }
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: keyVaultName }
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = { name: registryName }

resource dFoundry 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: foundry, properties: settings }
resource dSearch 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: search, properties: settings }
resource dDocintel 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: docintel, properties: settings }
resource dContentSafety 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: contentSafety, properties: settings }
resource dCosmos 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: cosmos, properties: settings }
resource dBus 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: bus, properties: settings }
resource dKv 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: kv, properties: settings }
resource dAcr 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = { name: 'diag-to-law', scope: acr, properties: settings }

output targets array = ['foundry', 'search', 'docintel', 'content-safety', 'cosmos', 'servicebus', 'keyvault', 'registry']
