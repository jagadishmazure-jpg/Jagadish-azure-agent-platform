// Key Vault (RBAC mode). Purge protection is off so `azd down --purge` fully cleans up a demo.
param location string
param tags object
param resourceToken string
param publicNetworkAccess string = 'Enabled'
param enablePurgeProtection bool = false

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${resourceToken}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: enablePurgeProtection ? true : null
    publicNetworkAccess: publicNetworkAccess
  }
}

output id string = kv.id
output name string = kv.name
output uri string = kv.properties.vaultUri
