output "id" {
  value = azurerm_api_management.this.id
}

output "name" {
  value = azurerm_api_management.this.name
}

output "canary_weight" {
  value = var.canary_weight
}

output "gateway_url" {
  value = azurerm_api_management.this.gateway_url
}
