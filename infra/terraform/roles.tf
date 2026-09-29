# Least-privilege data-plane roles, mirroring infra/modules/roles.bicep. Keys are static so
# the plan is stable even though principal ids are only known after apply.
locals {
  role_ids = {
    foundry_user               = "53ca6127-db72-4b80-b1b0-d745d6d5456d" # Azure AI User
    openai_user                = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd" # Cognitive Services OpenAI User
    cognitive_services_user    = "a97b65f3-24c7-4388-baec-2e87135dc908"
    search_index_data_reader   = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
    search_index_data_contrib  = "8ebe5a00-799e-43f5-93ac-243d3dce84a7"
    search_service_contributor = "7ca78c08-252a-4471-8644-bb5ff32d4ba0"
    service_bus_sender         = "69a216fc-b8fb-44d8-bc22-1f3c2cd27a39"
  }

  orch = module.identity.principal_ids["orchestrator"]

  workload_roles = {
    # orchestrator (BFF + underwriting agent)
    orch-foundry-user = { scope = module.foundry.account_id, role = "foundry_user", principal = local.orch }
    orch-openai-user  = { scope = module.foundry.account_id, role = "openai_user", principal = local.orch }
    orch-search-read  = { scope = module.search.id, role = "search_index_data_reader", principal = local.orch }
    orch-docintel     = { scope = module.docintel.id, role = "cognitive_services_user", principal = local.orch }
    orch-safety       = { scope = module.content_safety.id, role = "cognitive_services_user", principal = local.orch }
    orch-sb-send      = { scope = module.servicebus.id, role = "service_bus_sender", principal = local.orch }
    # service-to-service: Foundry agents' AI Search tool + Search integrated vectorizer
    foundry-search-read = { scope = module.search.id, role = "search_index_data_reader", principal = module.foundry.account_principal_id }
    search-openai-user  = { scope = module.foundry.account_id, role = "openai_user", principal = module.search.principal_id }
  }
  # tools identity only pulls images and reads secrets (granted in the registry / keyvault modules)

  deployer_roles = var.principal_id == "" ? {} : {
    deployer-search-svc  = { scope = module.search.id, role = "search_service_contributor", principal = var.principal_id }
    deployer-search-data = { scope = module.search.id, role = "search_index_data_contrib", principal = var.principal_id }
    deployer-foundry     = { scope = module.foundry.account_id, role = "foundry_user", principal = var.principal_id }
    deployer-openai      = { scope = module.foundry.account_id, role = "openai_user", principal = var.principal_id }
  }
}

resource "azurerm_role_assignment" "workload" {
  for_each                         = local.workload_roles
  scope                            = each.value.scope
  role_definition_id               = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_ids[each.value.role]}"
  principal_id                     = each.value.principal
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "deployer" {
  for_each           = local.deployer_roles
  scope              = each.value.scope
  role_definition_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_ids[each.value.role]}"
  principal_id       = each.value.principal
  principal_type     = var.principal_type
}
