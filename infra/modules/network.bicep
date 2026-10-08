// Optional private networking (privateLink=true): VNet with a Container Apps infrastructure subnet
// and a private-endpoint subnet, plus private DNS zones linked to the VNet. One NSG on both
// subnets, matching infra/terraform/modules/network.
param location string
param tags object
param resourceToken string
param addressPrefix string = '10.40.0.0/16'

var zones = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.search.windows.net'
  'privatelink.documents.azure.com'
  'privatelink.vaultcore.azure.net'
  'privatelink.servicebus.windows.net'
]

// One NSG for both subnets (default rules only; tighten per client policy), as in Terraform.
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-vnet-${resourceToken}'
  location: location
  tags: tags
  properties: { securityRules: [] }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${resourceToken}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [addressPrefix] }
    subnets: [
      {
        name: 'aca'
        properties: {
          addressPrefix: cidrSubnet(addressPrefix, 23, 0)
          networkSecurityGroup: { id: nsg.id }
          delegations: [{ name: 'aca', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      {
        name: 'pe'
        properties: { addressPrefix: cidrSubnet(addressPrefix, 24, 2), networkSecurityGroup: { id: nsg.id }, privateEndpointNetworkPolicies: 'Disabled' }
      }
    ]
  }
}

resource dns 'Microsoft.Network/privateDnsZones@2020-06-01' = [for z in zones: {
  name: z
  location: 'global'
  tags: tags
}]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (z, i) in zones: {
  parent: dns[i]
  name: 'link-${resourceToken}'
  location: 'global'
  properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
}]

output vnetId string = vnet.id
output nsgId string = nsg.id
output acaSubnetId string = vnet.properties.subnets[0].id
output peSubnetId string = vnet.properties.subnets[1].id
output zoneIds object = {
  cognitiveservices: dns[0].id
  openai: dns[1].id
  aiservices: dns[2].id
  search: dns[3].id
  cosmos: dns[4].id
  keyvault: dns[5].id
  servicebus: dns[6].id
}
