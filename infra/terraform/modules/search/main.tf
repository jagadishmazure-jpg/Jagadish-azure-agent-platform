# Azure AI Search: hybrid + vector + semantic ranker, Entra ID only (API keys disabled).
resource "azurerm_search_service" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  sku                           = var.sku
  replica_count                 = 1
  partition_count               = 1
  hosting_mode                  = "default"
  local_authentication_enabled  = false
  public_network_access_enabled = var.public_network_access_enabled
  semantic_search_sku           = var.sku == "free" ? null : var.semantic_search_sku

  identity {
    type = "SystemAssigned"
  }
}
