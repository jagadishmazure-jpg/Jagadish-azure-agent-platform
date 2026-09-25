// Azure AI Search: hybrid + vector + semantic ranker. Entra ID only (local keys disabled).
param location string
param tags object
param resourceToken string
@allowed(['free', 'basic', 'standard'])
param sku string = 'basic'
@description('Semantic ranker billing plan: free = monthly allowance (all tiers); standard = pay-as-you-go (Basic+).')
@allowed(['free', 'standard'])
param semanticSearch string = 'free'
param publicNetworkAccess string = 'enabled'

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: 'srch-${resourceToken}'
  location: location
  tags: tags
  sku: { name: sku }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
    semanticSearch: semanticSearch
  }
}

output id string = search.id
output name string = search.name
output endpoint string = 'https://${search.name}.search.windows.net'
output principalId string = search.identity.principalId
