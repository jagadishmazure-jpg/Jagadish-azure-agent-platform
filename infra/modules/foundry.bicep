// Microsoft Foundry (new resource model): an AIServices account with project management enabled,
// one Foundry project, model deployments, and a project connection to Azure AI Search (Entra ID auth).
param location string
param tags object
param resourceToken string
param projectName string = 'agent-platform'
param chatModelName string
param chatModelVersion string
param chatDeploymentSku string
param chatCapacity int
param embeddingModelName string
param embeddingModelVersion string
param embeddingCapacity int
param searchEndpoint string
param searchResourceId string
param publicNetworkAccess string = 'Enabled'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: 'aif-${resourceToken}'
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
    networkAcls: { defaultAction: publicNetworkAccess == 'Enabled' ? 'Allow' : 'Deny' }
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Azure Agent Platform'
    description: 'Mortgage underwriting multi-agent system + single-agent examples'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: chatModelName
  sku: { name: chatDeploymentSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModelName, version: chatModelVersion }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: embeddingModelName
  sku: { name: 'Standard', capacity: embeddingCapacity }
  properties: {
    model: { format: 'OpenAI', name: embeddingModelName, version: embeddingModelVersion }
  }
  dependsOn: [chat] // deployments on one account must be serialized
}

resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'aisearch'
  properties: {
    category: 'CognitiveSearch'
    target: searchEndpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: searchResourceId
    }
  }
}

output accountId string = account.id
output accountName string = account.name
output accountPrincipalId string = account.identity.principalId
output projectPrincipalId string = project.identity.principalId
output projectId string = project.id
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output openAiEndpoint string = 'https://${account.properties.customSubDomainName}.openai.azure.com/'
output chatDeploymentName string = chat.name
output embeddingDeploymentName string = embedding.name
output searchConnectionName string = searchConnection.name
