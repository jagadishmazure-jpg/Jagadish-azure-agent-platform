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

  assert {
    condition     = length(module.alerts) == 1 && length(module.alerts[0].metric_alert_names) == 4 && length(module.alerts[0].log_alert_names) == 3
    error_message = "alerts are on by default: 4 metric and 3 log alert rules"
  }

  assert {
    condition     = length(module.alerts[0].diagnostic_setting_targets) == 8
    error_message = "every data and AI resource sends logs and metrics to Log Analytics"
  }

  assert {
    condition     = length(module.defender) == 0
    error_message = "Defender for Cloud is subscription-wide and must stay opt-in"
  }
}

run "defender_opt_in" {
  command = plan

  variables {
    environment     = "dev"
    enable_defender = true
    alert_email     = "oncall@example.com"
  }

  assert {
    condition     = length(module.defender) == 1 && join(",", module.defender[0].plans) == "AI,Arm,CosmosDbs,KeyVaults"
    error_message = "enable_defender turns on the AI, Arm, CosmosDbs and KeyVaults plans"
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
    condition     = startswith(module.network[0].nsg_name, "nsg-")
    error_message = "private networking puts an NSG on both subnets"
  }

  assert {
    condition     = length(module.app) == 9
    error_message = "stand-ins add three apps"
  }
}
