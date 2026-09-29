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
  default = "basic"
  validation {
    condition     = contains(["free", "basic", "standard"], var.sku)
    error_message = "sku must be free, basic or standard."
  }
}

variable "semantic_search_sku" {
  description = "free = monthly allowance; standard = pay-as-you-go (Basic and above)."
  type        = string
  default     = "free"
}

variable "public_network_access_enabled" {
  type    = bool
  default = true
}
