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

variable "kind" {
  type = string
  validation {
    condition     = contains(["FormRecognizer", "ContentSafety", "AIServices"], var.kind)
    error_message = "kind must be FormRecognizer, ContentSafety or AIServices."
  }
}

variable "sku" {
  type    = string
  default = "S0"
}

variable "identity_id" {
  description = "Optional user-assigned identity id attached to the account."
  type        = string
  default     = ""
}

variable "public_network_access_enabled" {
  type    = bool
  default = true
}
