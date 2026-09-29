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

variable "database_name" {
  type = string
}

variable "containers" {
  description = "container name -> { partition_key, ttl } (ttl -1 = on without expiry, null = off)"
  type = map(object({
    partition_key = string
    ttl           = optional(number)
  }))
}

variable "data_contributor_principal_ids" {
  description = "static key -> principal id granted the built-in data contributor role"
  type        = map(string)
  default     = {}
}

variable "public_network_access_enabled" {
  type    = bool
  default = true
}
