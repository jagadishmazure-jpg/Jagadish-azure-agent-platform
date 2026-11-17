// Shared Application Insights workbook. Queries are the files under observability/ so the
// dashboard deployed by azd matches the KQL checked into Git.
param location string
param tags object
param appInsightsId string

var tiles = [
  { name: 'requests', title: 'Requests', query: loadTextContent('../../observability/requests.kql') }
  { name: 'dependencies', title: 'Dependencies', query: loadTextContent('../../observability/dependencies.kql') }
  { name: 'exceptions', title: 'Exceptions', query: loadTextContent('../../observability/exceptions.kql') }
  { name: 'cosmos-checkpoints', title: 'Cosmos checkpoints', query: loadTextContent('../../observability/cosmos-checkpoints.kql') }
  { name: 'canary', title: 'Canary prompt split', query: loadTextContent('../../observability/canary.kql') }
]

var intro = [
  {
    type: 1
    content: {
      json: '## Agent platform operations\n\nRequest health, dependencies (Foundry, AI Search, Cosmos checkpoints), exceptions, and the canary prompt split.'
    }
    name: 'intro'
  }
]

var kqlItems = [
  for tile in tiles: {
    type: 3
    content: {
      version: 'KqlItem/1.0'
      query: tile.query
      size: 0
      title: tile.title
      timeContext: { durationMs: 86400000 }
      queryType: 0
      resourceType: 'microsoft.insights/components'
    }
    name: tile.name
  }
]

var notebook = {
  version: 'Notebook/1.0'
  items: concat(intro, kqlItems)
}

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid(appInsightsId, 'agent-platform-ops')
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'Agent platform operations'
    category: 'workbook'
    sourceId: appInsightsId
    serializedData: string(notebook)
  }
}

output name string = workbook.name
output displayName string = 'Agent platform operations'
