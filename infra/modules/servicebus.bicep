// Service Bus for queued writes (LOS status updates, CRM/ERP postings) — the outbox pattern.
param location string
param tags object
param resourceToken string
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

resource ns 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: 'sb-${resourceToken}'
  location: location
  tags: tags
  sku: { name: sku, tier: sku }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
  }
}

resource queues 'Microsoft.ServiceBus/namespaces/queues@2024-01-01' = [for q in ['los-writes', 'agent-outbox']: {
  parent: ns
  name: q
  properties: {
    maxDeliveryCount: 5
    lockDuration: 'PT1M'
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: 'P7D'
    // duplicate detection needs Standard+; idempotency keys are enforced by consumers regardless
    requiresDuplicateDetection: sku != 'Basic'
  }
}]

output id string = ns.id
output name string = ns.name
output fqdn string = '${ns.name}.servicebus.windows.net'
