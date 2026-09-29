# Single-purpose Cognitive Services account (Document Intelligence or Content Safety), keyless.
resource "azurerm_cognitive_account" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  kind                          = var.kind
  sku_name                      = var.sku
  custom_subdomain_name         = var.name
  local_auth_enabled            = false
  public_network_access_enabled = var.public_network_access_enabled

  dynamic "identity" {
    for_each = var.identity_id == "" ? [] : [1]
    content {
      type         = "UserAssigned"
      identity_ids = [var.identity_id]
    }
  }

  network_acls {
    default_action = var.public_network_access_enabled ? "Allow" : "Deny"
  }
}
