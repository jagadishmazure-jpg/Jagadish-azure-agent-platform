// Azure Container Registry for azd-built images (admin user disabled; pulls via managed identity).
param location string
param tags object
@minLength(3)
param resourceToken string
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${resourceToken}'
  location: location
  tags: tags
  sku: { name: sku }
  properties: { adminUserEnabled: false }
}

output id string = acr.id
output name string = acr.name
output loginServer string = acr.properties.loginServer
