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
