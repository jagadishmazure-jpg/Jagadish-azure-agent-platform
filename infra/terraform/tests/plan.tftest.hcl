# Offline plan tests: mocked providers, no Azure credentials, nothing created.
# Run with:  terraform init -backend=false && terraform test
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "azapi" {}

run "dev_cost_min" {
  command = plan

  variables {
    environment  = "dev"
    cost_profile = "cost-min"
  }

  assert {
    condition     = azurerm_resource_group.this.name == "rg-agentplat-dev-eus2-001"
    error_message = "resource group must follow the CAF pattern"
  }

  assert {
    condition     = alltrue([for k in ["env", "owner", "project", "cost-center"] : contains(keys(azurerm_resource_group.this.tags), k)])
    error_message = "required tags missing"
  }

  assert {
    condition     = length(module.private_endpoint) == 0 && length(module.network) == 0
    error_message = "dev must not create private networking"
  }

  assert {
    condition     = module.servicebus.name != "" && local.service_bus_sku == "Basic" && local.apim_sku == "Consumption"
    error_message = "cost-min must pick Basic Service Bus and Consumption APIM"
  }

  assert {
    condition     = length(module.app) == 6
    error_message = "six core container apps expected"
  }
}

run "prod_private" {
  command = plan

  variables {
    environment                = "prod"
    cost_profile               = "standard"
    private_link               = true
    key_vault_purge_protection = true
    deploy_vendor_standins     = true
  }

  assert {
    condition     = length(module.private_endpoint) == 7 && local.service_bus_sku == "Premium"
    error_message = "private link must add 7 private endpoints and force Service Bus Premium"
  }

  assert {
    condition     = length(module.app) == 9
    error_message = "stand-ins add three apps"
  }
}
