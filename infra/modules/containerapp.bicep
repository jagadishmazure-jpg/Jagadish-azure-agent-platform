// One Container App (BFF, MCP server, or A2A agent). azd replaces the placeholder image on deploy.
param location string
param tags object
param name string
param serviceName string
param environmentId string
param identityId string
param registryServer string
param external bool = false
param targetPort int = 8080
param env array = []
param command array = []
param minReplicas int = 0
param maxReplicas int = 3
@description('Liveness probe path; empty disables the probe (MCP servers expose only /mcp).')
param healthPath string = '/healthz'
param cpu string = '0.5'
param memory string = '1Gi'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': serviceName })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: external
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: !external // internal east-west traffic stays inside the environment
      }
      registries: [{ server: registryServer, identity: identityId }]
    }
    template: {
      containers: [
        {
          name: 'main'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          command: empty(command) ? null : command
          env: concat([{ name: 'PORT', value: string(targetPort) }], env)
          resources: { cpu: json(cpu), memory: memory }
          probes: empty(healthPath) ? [] : [
            { type: 'Liveness', httpGet: { path: healthPath, port: targetPort }, periodSeconds: 30 }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [{ name: 'http', http: { metadata: { concurrentRequests: '20' } } }]
      }
    }
  }
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
