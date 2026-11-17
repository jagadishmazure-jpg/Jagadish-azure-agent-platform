locals {
  queries = {
    requests             = file("${path.module}/../../../../observability/requests.kql")
    dependencies         = file("${path.module}/../../../../observability/dependencies.kql")
    exceptions           = file("${path.module}/../../../../observability/exceptions.kql")
    "cosmos-checkpoints" = file("${path.module}/../../../../observability/cosmos-checkpoints.kql")
    canary               = file("${path.module}/../../../../observability/canary.kql")
  }
  titles = {
    requests             = "Requests"
    dependencies         = "Dependencies"
    exceptions           = "Exceptions"
    "cosmos-checkpoints" = "Cosmos checkpoints"
    canary               = "Canary prompt split"
  }
  tiles = [
    for name in ["requests", "dependencies", "exceptions", "cosmos-checkpoints", "canary"] : {
      type = 3
      name = name
      content = {
        version      = "KqlItem/1.0"
        query        = local.queries[name]
        size         = 0
        title        = local.titles[name]
        timeContext  = { durationMs = 86400000 }
        queryType    = 0
        resourceType = "microsoft.insights/components"
      }
    }
  ]
}

resource "azurerm_application_insights_workbook" "ops" {
  # Stable id so a re-apply updates the same workbook instead of creating another.
  name                = "11111111-2222-4333-8444-555555555555"
  resource_group_name = var.resource_group_name
  location            = var.location
  display_name        = "Agent platform operations"
  source_id           = var.app_insights_id
  category            = "workbook"
  tags                = var.tags
  data_json = jsonencode({
    version = "Notebook/1.0"
    items = concat(
      [
        {
          type = 1
          name = "intro"
          content = {
            json = "## Agent platform operations\n\nRequest health, dependencies (Foundry, AI Search, Cosmos checkpoints), exceptions, and the canary prompt split."
          }
        }
      ],
      local.tiles
    )
  })
}
