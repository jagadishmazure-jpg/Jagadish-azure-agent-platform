// Cosmos DB for NoSQL, serverless (pay per RU + storage, no provisioned throughput).
// Containers: MAF workflow checkpoints (pk /workflow_name, as CosmosCheckpointStorage expects),
// agent memory (pk /tenant_id), run index (pk /tenant_id).
param location string
param tags object
param resourceToken string
param databaseName string = 'agentplatform'
param dataContributorPrincipalIds array
param publicNetworkAccess string = 'Enabled'

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: 'cosmos-${resourceToken}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    capabilities: [{ name: 'EnableServerless' }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
    minimalTlsVersion: 'Tls12'
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: account
  name: databaseName
  properties: { resource: { id: databaseName } }
}

var containers = [
  { name: 'checkpoints', pk: '/workflow_name', ttl: 2592000 }
  { name: 'memory', pk: '/tenant_id', ttl: -1 }
  { name: 'runs', pk: '/tenant_id', ttl: 7776000 }
]

resource cs 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = [for c in containers: {
  parent: db
  name: c.name
  properties: {
    resource: {
      id: c.name
      partitionKey: { paths: [c.pk], kind: 'Hash' }
      defaultTtl: c.ttl
    }
  }
}]

// Built-in data-plane role "Cosmos DB Built-in Data Contributor" (00000000-0000-0000-0000-000000000002).
resource dataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = [for pid in dataContributorPrincipalIds: {
  parent: account
  name: guid(account.id, pid, 'cosmos-data-contributor')
  properties: {
    principalId: pid
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: '${account.id}/dbs/${databaseName}'
  }
}]

output id string = account.id
output name string = account.name
output endpoint string = account.properties.documentEndpoint
output databaseName string = databaseName
