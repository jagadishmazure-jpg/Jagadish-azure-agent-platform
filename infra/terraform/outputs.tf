# Same output names as infra/main.bicep so scripts and the pipeline work with either tool.
output "AZURE_LOCATION" {
  value = var.location
}

output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.this.name
}

output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  value = module.registry.login_server
}

output "AZURE_CONTAINER_REGISTRY_NAME" {
  value = module.registry.name
}

output "FOUNDRY_PROJECT_ENDPOINT" {
  value = module.foundry.project_endpoint
}

output "FOUNDRY_MODEL" {
  value = module.foundry.chat_deployment_name
}

output "AZURE_OPENAI_ENDPOINT" {
  value = module.foundry.openai_endpoint
}

output "AZURE_OPENAI_EMBEDDING_DEPLOYMENT" {
  value = module.foundry.embedding_deployment_name
}

output "AZURE_SEARCH_ENDPOINT" {
  value = module.search.endpoint
}

output "AZURE_SEARCH_CONNECTION" {
  value = module.foundry.search_connection_name
}

output "AZURE_DOCINTEL_ENDPOINT" {
  value = module.docintel.endpoint
}

output "AZURE_CONTENT_SAFETY_ENDPOINT" {
  value = module.content_safety.endpoint
}

output "AZURE_COSMOS_ENDPOINT" {
  value = module.cosmos.endpoint
}

output "AZURE_SERVICEBUS_NAMESPACE" {
  value = module.servicebus.fqdn
}

output "AZURE_KEY_VAULT_URI" {
  value = module.keyvault.uri
}

output "APIM_GATEWAY_URL" {
  value = module.apim.gateway_url
}

output "BFF_URL" {
  value = module.app["ca-bff"].url
}

output "EVAL_MODEL_DEPLOYMENT" {
  value = module.foundry.chat_deployment_name
}
