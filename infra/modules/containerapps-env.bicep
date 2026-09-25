// Container Apps managed environment (Consumption plan: billed per vCPU-second / GiB-second / request,
// scale-to-zero). Optional VNet integration when privateLink is on.
param location string
param tags object
param resourceToken string
param logAnalyticsName string
param infrastructureSubnetId string = ''

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    vnetConfiguration: empty(infrastructureSubnetId) ? null : {
      infrastructureSubnetId: infrastructureSubnetId
      internal: false
    }
  }
}

output id string = env.id
output name string = env.name
output defaultDomain string = env.properties.defaultDomain
