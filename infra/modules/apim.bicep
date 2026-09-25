// API Management as the AI gateway in front of the BFF (and, optionally, A2A agents):
// Entra ID JWT validation, identity headers derived from claims, rate limiting, and a global
// kill switch driven by a named value (flip `agents-enabled` to false → every agent call gets 503).
param location string
param tags object
param resourceToken string
@allowed(['Consumption', 'Developer', 'BasicV2', 'StandardV2'])
param sku string = 'Consumption'
param publisherEmail string
param publisherName string = 'Jagadish Meduri'
param bffUrl string
@description('Entra ID tenant for JWT validation. Empty = skip validation (demo only).')
param entraTenantId string = ''
@description('Expected audience (app ID URI) of tokens presented to the gateway.')
param entraAudience string = ''

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: 'apim-${resourceToken}'
  location: location
  tags: tags
  sku: { name: sku, capacity: sku == 'Consumption' ? 0 : 1 }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource killSwitch 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'agents-enabled'
  properties: { displayName: 'agents-enabled', value: 'true', secret: false }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'agent-platform'
  properties: {
    displayName: 'Agent Platform BFF'
    path: 'agents'
    protocols: ['https']
    serviceUrl: bffUrl
    subscriptionRequired: true
  }
}

resource ops 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = [for op in [
  { name: 'underwrite', method: 'POST', url: '/loans/{loan_id}/underwrite', params: ['loan_id'] }
  { name: 'get-run', method: 'GET', url: '/runs/{run_id}', params: ['run_id'] }
  { name: 'decide', method: 'POST', url: '/runs/{run_id}/decision', params: ['run_id'] }
  { name: 'directory', method: 'GET', url: '/directory', params: [] }
  { name: 'chat-hr', method: 'POST', url: '/chat/hr', params: [] }
  { name: 'chat-it', method: 'POST', url: '/chat/it', params: [] }
]: {
  parent: api
  name: op.name
  properties: {
    displayName: op.name
    method: op.method
    urlTemplate: op.url
    templateParameters: [for p in op.params: { name: p, type: 'string', required: true }]
  }
}]

var jwtPolicy = empty(entraTenantId) ? '' : '<validate-jwt header-name="Authorization" failed-validation-httpcode="401" output-token-variable-name="jwt"><openid-config url="${environment().authentication.loginEndpoint}${entraTenantId}/v2.0/.well-known/openid-configuration" /><audiences><audience>${entraAudience}</audience></audiences></validate-jwt><set-header name="x-user" exists-action="override"><value>@(((Jwt)context.Variables["jwt"]).Claims.GetValueOrDefault("oid", ""))</value></set-header><set-header name="x-tenant-id" exists-action="override"><value>@(((Jwt)context.Variables["jwt"]).Claims.GetValueOrDefault("tid", ""))</value></set-header><set-header name="x-groups" exists-action="override"><value>@(string.Join(",", ((Jwt)context.Variables["jwt"]).Claims.GetValueOrDefault("roles", new string[0])))</value></set-header>'
var stripSpoofable = '<set-header name="x-user" exists-action="delete" /><set-header name="x-groups" exists-action="delete" />'

resource policy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: '<policies><inbound><base /><choose><when condition="@(&quot;{{agents-enabled}}&quot; != &quot;true&quot;)"><return-response><set-status code="503" reason="Agents disabled by kill switch" /></return-response></when></choose>${empty(entraTenantId) ? '' : stripSpoofable}${jwtPolicy}<rate-limit calls="60" renewal-period="60" /><set-header name="traceparent" exists-action="skip"><value>@($"00-{Guid.NewGuid().ToString("N")}-{Guid.NewGuid().ToString("N").Substring(0,16)}-01")</value></set-header></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>'
  }
  dependsOn: [killSwitch]
}

output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
