// Single-purpose Cognitive Services account (Document Intelligence or Content Safety).
param location string
param tags object
param name string
@allowed(['FormRecognizer', 'ContentSafety'])
param kind string
@allowed(['F0', 'S0'])
param sku string = 'S0'
param publicNetworkAccess string = 'Enabled'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: kind
  sku: { name: sku }
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
  }
}

output id string = account.id
output name string = account.name
output endpoint string = account.properties.endpoint
