# azure-agent-platform: Terraform mirror of infra/main.bicep. Same resources, same cost-min
# defaults, CAF names and the env/owner/project/cost-center tag set.
data "azurerm_client_config" "current" {}

module "naming" {
  source      = "./modules/naming"
  workload    = var.workload
  environment = var.environment
  location    = var.location
  instance    = var.instance
  suffix      = var.name_suffix
}

resource "azurerm_resource_group" "this" {
  name     = module.naming.resource_group
  location = var.location
  tags     = local.tags
}

module "identity" {
  source              = "./modules/identity"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  identities = {
    orchestrator = "id-orch-${module.naming.base}"
    tools        = "id-tools-${module.naming.base}"
  }
}

module "monitoring" {
  source              = "./modules/monitoring"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  log_analytics_name  = module.naming.log_analytics
  app_insights_name   = module.naming.app_insights
  daily_quota_gb      = local.p.log_quota_gb
}

module "network" {
  source              = "./modules/network"
  count               = var.private_link ? 1 : 0
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  name                = module.naming.vnet
  dns_zones = {
    cognitiveservices = "privatelink.cognitiveservices.azure.com"
    openai            = "privatelink.openai.azure.com"
    aiservices        = "privatelink.services.ai.azure.com"
    search            = "privatelink.search.windows.net"
    cosmos            = "privatelink.documents.azure.com"
    keyvault          = "privatelink.vaultcore.azure.net"
    servicebus        = "privatelink.servicebus.windows.net"
  }
}

module "search" {
  source                        = "./modules/search"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.location
  tags                          = local.tags
  name                          = local.n["srch"]
  sku                           = local.search_sku
  public_network_access_enabled = local.public_access
}

module "foundry" {
  source                        = "./modules/foundry"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.location
  tags                          = local.tags
  name                          = local.n["aif"]
  project_name                  = "agent-platform"
  project_display_name          = "Azure Agent Platform"
  project_description           = "Mortgage underwriting multi-agent system + single-agent examples"
  chat_model_name               = var.chat_model_name
  chat_model_version            = var.chat_model_version
  chat_deployment_sku           = var.chat_deployment_sku
  chat_capacity                 = coalesce(var.chat_capacity, local.p.capacity)
  embedding_model_name          = var.embedding_model_name
  embedding_model_version       = var.embedding_model_version
  embedding_capacity            = coalesce(var.embedding_capacity, local.p.capacity)
  search_endpoint               = module.search.endpoint
  search_resource_id            = module.search.id
  connect_search                = true
  public_network_access_enabled = local.public_access
}

module "docintel" {
  source                        = "./modules/cognitive"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.location
  tags                          = local.tags
  name                          = local.n["di"]
  kind                          = "FormRecognizer"
  sku                           = var.doc_intel_sku
  public_network_access_enabled = local.public_access
}

module "content_safety" {
  source                        = "./modules/cognitive"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.location
  tags                          = local.tags
  name                          = local.n["cs"]
  kind                          = "ContentSafety"
  sku                           = var.content_safety_sku
  public_network_access_enabled = local.public_access
}

module "cosmos" {
  source              = "./modules/cosmos"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  name                = local.n["cosmos"]
  database_name       = "agentplatform"
  containers = {
    checkpoints = { partition_key = "/workflow_name", ttl = 2592000 }
    memory      = { partition_key = "/tenant_id", ttl = -1 }
    runs        = { partition_key = "/tenant_id", ttl = 7776000 }
  }
  data_contributor_principal_ids = merge(
    { orchestrator = module.identity.principal_ids["orchestrator"] },
    var.principal_id == "" ? {} : { deployer = var.principal_id },
  )
  public_network_access_enabled = local.public_access
}

module "servicebus" {
  source                        = "./modules/servicebus"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.location
  tags                          = local.tags
  name                          = local.n["sbns"]
  sku                           = local.service_bus_sku
  queues                        = ["los-writes", "agent-outbox"]
  public_network_access_enabled = local.public_access
}

module "keyvault" {
  source                        = "./modules/keyvault"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.location
  tags                          = local.tags
  name                          = module.naming.key_vault
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  purge_protection_enabled      = var.key_vault_purge_protection
  public_network_access_enabled = local.public_access
  secret_reader_principal_ids   = module.identity.principal_ids
}

module "registry" {
  source              = "./modules/registry"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  name                = module.naming.container_registry
  pull_principal_ids  = module.identity.principal_ids
}

# ---- private endpoints (privateLink only) ----
locals {
  pe_targets = {
    foundry       = { id = module.foundry.account_id, group = "account", zones = ["cognitiveservices", "openai", "aiservices"] }
    search        = { id = module.search.id, group = "searchService", zones = ["search"] }
    docintel      = { id = module.docintel.id, group = "account", zones = ["cognitiveservices"] }
    contentsafety = { id = module.content_safety.id, group = "account", zones = ["cognitiveservices"] }
    cosmos        = { id = module.cosmos.id, group = "Sql", zones = ["cosmos"] }
    keyvault      = { id = module.keyvault.id, group = "vault", zones = ["keyvault"] }
    servicebus    = { id = module.servicebus.id, group = "namespace", zones = ["servicebus"] }
  }
}

module "private_endpoint" {
  source              = "./modules/private-endpoint"
  for_each            = var.private_link ? local.pe_targets : {}
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  name                = "pe-${each.key}-${module.naming.base}"
  subnet_id           = module.network[0].pe_subnet_id
  target_resource_id  = each.value.id
  group_id            = each.value.group
  dns_zone_ids        = [for z in each.value.zones : module.network[0].zone_ids[z]]
}

module "aca_env" {
  source                     = "./modules/containerapps-env"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tags                       = local.tags
  name                       = module.naming.container_apps_env
  log_analytics_workspace_id = module.monitoring.log_analytics_id
  infrastructure_subnet_id   = var.private_link ? module.network[0].aca_subnet_id : ""
}

# ---- application settings shared by the services ----
locals {
  common_env = {
    AAP_MODE                              = "azure"
    AAP_A2A_REMOTE                        = "1"
    APPLICATIONINSIGHTS_CONNECTION_STRING = module.monitoring.app_insights_connection_string
    AZURE_KEY_VAULT_URI                   = module.keyvault.uri
    A2A_UNDERWRITING_AGENT_URL            = "http://ca-underwriting-agent"
    A2A_CRM_AGENT_URL                     = "http://ca-crm-agent"
    A2A_ERP_AGENT_URL                     = "http://ca-erp-agent"
    A2A_DYNAMICS_CRM_STANDIN_URL          = "http://ca-dynamics-crm-standin"
    A2A_SALESFORCE_CRM_STANDIN_URL        = "http://ca-salesforce-crm-standin"
    A2A_SAP_ERP_STANDIN_URL               = "http://ca-sap-erp-standin"
    MCP_CREDIT_BUREAU_URL                 = "http://ca-mcp-credit-bureau/mcp"
    MCP_LOS_URL                           = "http://ca-mcp-los/mcp"
  }
  orchestrator_env = merge(local.common_env, {
    AZURE_CLIENT_ID                   = module.identity.client_ids["orchestrator"]
    FOUNDRY_PROJECT_ENDPOINT          = module.foundry.project_endpoint
    FOUNDRY_MODEL                     = module.foundry.chat_deployment_name
    AZURE_OPENAI_ENDPOINT             = module.foundry.openai_endpoint
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = module.foundry.embedding_deployment_name
    AZURE_SEARCH_ENDPOINT             = module.search.endpoint
    AZURE_DOCINTEL_ENDPOINT           = module.docintel.endpoint
    AZURE_CONTENT_SAFETY_ENDPOINT     = module.content_safety.endpoint
    AZURE_COSMOS_ENDPOINT             = module.cosmos.endpoint
    AZURE_SERVICEBUS_NAMESPACE        = module.servicebus.fqdn
  })
  tools_env = merge(local.common_env, { AZURE_CLIENT_ID = module.identity.client_ids["tools"] })

  core_apps = {
    "ca-bff"                = { service = "bff", external = true, orchestrator = true, command = [] }
    "ca-underwriting-agent" = { service = "a2a-underwriting", external = false, orchestrator = true, command = ["python", "-m", "agentplatform.a2a", "underwriting-agent"] }
    "ca-crm-agent"          = { service = "a2a-crm", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.a2a", "crm-agent"] }
    "ca-erp-agent"          = { service = "a2a-erp", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.a2a", "erp-agent"] }
    "ca-mcp-credit-bureau"  = { service = "mcp-credit-bureau", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.mcp_servers", "credit-bureau"] }
    "ca-mcp-los"            = { service = "mcp-los", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.mcp_servers", "los"] }
  }
  standin_apps = {
    "ca-dynamics-crm-standin"   = { service = "a2a-dynamics-standin", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.a2a", "dynamics-crm-standin"] }
    "ca-salesforce-crm-standin" = { service = "a2a-salesforce-standin", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.a2a", "salesforce-crm-standin"] }
    "ca-sap-erp-standin"        = { service = "a2a-sap-standin", external = false, orchestrator = false, command = ["python", "-m", "agentplatform.a2a", "sap-erp-standin"] }
  }
  apps = merge(local.core_apps, var.deploy_vendor_standins ? local.standin_apps : {})
}

module "app" {
  source              = "./modules/containerapp"
  for_each            = local.apps
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
  name                = each.key
  service_name        = each.value.service
  environment_id      = module.aca_env.id
  identity_id         = each.value.orchestrator ? module.identity.ids["orchestrator"] : module.identity.ids["tools"]
  registry_server     = module.registry.login_server
  image               = var.container_image
  external            = each.value.external
  command             = each.value.command
  env                 = each.value.orchestrator ? local.orchestrator_env : local.tools_env
  min_replicas        = local.p.min_replicas
  health_path         = startswith(each.value.service, "mcp-") ? "" : "/healthz"

  # AcrPull must exist before the first image pull
  depends_on = [module.registry, azurerm_role_assignment.workload]
}

module "apim" {
  source              = "./modules/apim"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  name                = local.n["apim"]
  sku                 = local.apim_sku
  publisher_email     = var.apim_publisher_email
  api_name            = "agent-platform"
  api_display_name    = "Agent Platform BFF"
  api_path            = "agents"
  backend_url         = module.app["ca-bff"].url
  entra_tenant_id     = var.entra_tenant_id
  entra_audience      = var.entra_audience
  operations = {
    underwrite = { method = "POST", url = "/loans/{loan_id}/underwrite", params = ["loan_id"] }
    get-run    = { method = "GET", url = "/runs/{run_id}", params = ["run_id"] }
    decide     = { method = "POST", url = "/runs/{run_id}/decision", params = ["run_id"] }
    directory  = { method = "GET", url = "/directory", params = [] }
    chat-hr    = { method = "POST", url = "/chat/hr", params = [] }
    chat-it    = { method = "POST", url = "/chat/it", params = [] }
  }
}
