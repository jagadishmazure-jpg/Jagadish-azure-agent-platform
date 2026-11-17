variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "name" {
  type = string
}

variable "sku" {
  type    = string
  default = "Consumption"
  validation {
    condition     = contains(["Consumption", "Developer", "BasicV2", "StandardV2"], var.sku)
    error_message = "sku must be Consumption, Developer, BasicV2 or StandardV2."
  }
}

variable "publisher_name" {
  type    = string
  default = "Jagadish Meduri"
}

variable "publisher_email" {
  type = string
}

variable "api_name" {
  type = string
}

variable "api_display_name" {
  type = string
}

variable "api_path" {
  type = string
}

variable "backend_url" {
  type = string
}

variable "subscription_required" {
  type    = bool
  default = true
}

variable "operations" {
  description = "operation id -> { method, url, params }"
  type = map(object({
    method = string
    url    = string
    params = list(string)
  }))
  default = {}
}

variable "entra_tenant_id" {
  description = "Entra tenant for JWT validation; empty = skip validation (demo only)."
  type        = string
  default     = ""
}

variable "entra_audience" {
  type    = string
  default = ""
}

variable "rate_limit_calls" {
  type    = number
  default = 60
}

variable "canary_weight" {
  description = "Percent of calls sent to the canary prompt and model. 0 keeps every call on stable."
  type        = number
  default     = 0
  validation {
    condition     = var.canary_weight >= 0 && var.canary_weight <= 100
    error_message = "canary_weight must be between 0 and 100."
  }
}

variable "stable_prompt_ref" {
  type    = string
  default = "mortgage.critic@1.0.0"
}

variable "canary_prompt_ref" {
  type    = string
  default = "mortgage.critic@1.1.0"
}

variable "stable_model" {
  type    = string
  default = "gpt-5-mini"
}

variable "canary_model" {
  type    = string
  default = "gpt-5-mini"
}

variable "canary_backend_url" {
  description = "Empty uses the same backend URL as the stable BFF."
  type        = string
  default     = ""
}

variable "gateway_token" {
  description = "Token APIM sends and the BFF requires before trusting identity headers. Empty skips it."
  type        = string
  default     = ""
}
