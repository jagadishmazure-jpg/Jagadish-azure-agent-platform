# ---- naming / tagging ----
variable "workload" {
  description = "Workload token used in CAF names."
  type        = string
  default     = "agentplat"
}

variable "environment" {
  description = "dev | test | prod"
  type        = string
}

variable "location" {
  description = "Primary region. Must offer the chosen models (GlobalStandard) and the semantic ranker."
  type        = string
  default     = "eastus2"
}

variable "instance" {
  type    = string
  default = "001"
}

variable "name_suffix" {
  description = "Optional suffix for globally unique names (set when forking to avoid collisions)."
  type        = string
  default     = ""
}

variable "owner" {
  type    = string
  default = "jagadish.meduri"
}

variable "project" {
  type    = string
  default = "azure-agent-platform"
}

variable "cost_center" {
  type    = string
  default = "portfolio"
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}

# ---- deployment shape ----
variable "cost_profile" {
  description = "cost-min = cheapest SKUs that still exercise every feature; standard = always-on."
  type        = string
  default     = "cost-min"
  validation {
    condition     = contains(["cost-min", "standard"], var.cost_profile)
    error_message = "cost_profile must be cost-min or standard."
  }
}

variable "private_link" {
  description = "Private endpoints + VNet-integrated Container Apps (adds hourly cost; forces Service Bus Premium)."
  type        = bool
  default     = false
}

variable "deploy_vendor_standins" {
  description = "Deploy the Dynamics-style / Salesforce-style / SAP-style stand-in A2A agents."
  type        = bool
  default     = false
}

variable "principal_id" {
  description = "Object id of the deploying principal (seeds indexes, registers agents). Empty = skip."
  type        = string
  default     = ""
}

variable "principal_type" {
  type    = string
  default = "ServicePrincipal"
  validation {
    condition     = contains(["User", "ServicePrincipal"], var.principal_type)
    error_message = "principal_type must be User or ServicePrincipal."
  }
}

variable "key_vault_purge_protection" {
  type    = bool
  default = false
}

# ---- models ----
variable "chat_model_name" {
  type    = string
  default = "gpt-5-mini"
}

variable "chat_model_version" {
  type    = string
  default = "2025-08-07"
}

variable "chat_deployment_sku" {
  type    = string
  default = "GlobalStandard"
}

variable "chat_capacity" {
  description = "null = profile default (10 cost-min, 50 standard)."
  type        = number
  default     = null
}

variable "embedding_model_name" {
  type    = string
  default = "text-embedding-3-small"
}

variable "embedding_model_version" {
  type    = string
  default = "1"
}

variable "embedding_capacity" {
  type    = number
  default = null
}

# ---- SKU overrides (empty = profile default) ----
variable "apim_sku" {
  type    = string
  default = ""
}

variable "search_sku" {
  type    = string
  default = ""
}

variable "service_bus_sku" {
  type    = string
  default = ""
}

variable "doc_intel_sku" {
  type    = string
  default = "S0"
}

variable "content_safety_sku" {
  type    = string
  default = "S0"
}

variable "apim_publisher_email" {
  type    = string
  default = "noreply@example.com"
}

variable "entra_tenant_id" {
  type    = string
  default = ""
}

variable "entra_audience" {
  type    = string
  default = ""
}

variable "container_image" {
  description = "Initial image for every app; the deploy workflow rolls real images afterwards."
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}
