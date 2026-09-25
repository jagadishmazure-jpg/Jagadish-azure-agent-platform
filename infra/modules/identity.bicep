// Workload identities. Two user-assigned MIs so blast radius follows the plane:
//  - orchestrator: BFF + underwriting agent (models, search, cosmos, service bus, doc intel, content safety)
//  - tools: MCP servers + CRM/ERP/stand-in A2A agents (pull images, read secrets; nothing else)
param location string
param tags object
param resourceToken string

resource orchestrator 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-orch-${resourceToken}'
  location: location
  tags: tags
}

resource tools 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-tools-${resourceToken}'
  location: location
  tags: tags
}

output orchestratorId string = orchestrator.id
output orchestratorPrincipalId string = orchestrator.properties.principalId
output orchestratorClientId string = orchestrator.properties.clientId
output toolsId string = tools.id
output toolsPrincipalId string = tools.properties.principalId
output toolsClientId string = tools.properties.clientId
