// Log Analytics (pay-per-GB ingestion) + workspace-based Application Insights (OpenTelemetry sink).
param location string
param tags object
param resourceToken string
param retentionInDays int = 30
@description('Daily ingestion cap in GB (-1 = no cap). cost-min profile caps at 1 GB/day.')
param dailyQuotaGb int = 1

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: retentionInDays
    workspaceCapping: { dailyQuotaGb: dailyQuotaGb }
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    DisableLocalAuth: false // connection-string ingestion for the OTel distro; flip to true + MI auth for prod
  }
}

output logAnalyticsId string = law.id
output logAnalyticsName string = law.name
output appInsightsConnectionString string = appi.properties.ConnectionString
output appInsightsId string = appi.id
