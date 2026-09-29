locals {
  profiles = {
    "cost-min" = { apim = "Consumption", search = "basic", service_bus = "Basic", min_replicas = 0, log_quota_gb = 1, capacity = 10 }
    standard   = { apim = "Developer", search = "standard", service_bus = "Standard", min_replicas = 1, log_quota_gb = -1, capacity = 50 }
  }
  p = local.profiles[var.cost_profile]

  service_bus_sku = var.private_link ? "Premium" : coalesce(var.service_bus_sku, local.p.service_bus)
  search_sku      = coalesce(var.search_sku, local.p.search)
  apim_sku        = coalesce(var.apim_sku, local.p.apim)
  public_access   = !var.private_link

  tags = merge({
    env            = var.environment
    owner          = var.owner
    project        = var.project
    "cost-center"  = var.cost_center
    workload       = var.workload
    "cost-profile" = var.cost_profile
    "managed-by"   = "terraform"
  }, var.extra_tags)

  n = module.naming.prefix_for
}
