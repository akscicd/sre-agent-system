variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Default Region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Default Zone"
  type        = string
  default     = "us-central1-a"
}


variable "network_config" {
  description = "Networking Configuration"
  type = object({
    vpc_name    = string
    subnet_name = string
    subnet_cidr = string
  })
}

variable "jenkins_config" {
  description = "Jenkins VM Configuration"
  type = object({
    vm_name             = string
    machine_type        = string
    deletion_protection = bool
    tags                = list(string)
    boot_image          = string
    boot_size           = number
    static_internal_ip  = optional(string)
  })
}

variable "agent_config" {
  description = "Agent VM Configuration"
  type = object({
    vm_name             = string
    machine_type        = string
    deletion_protection = bool
    tags                = list(string)
    boot_image          = string
    boot_size           = number
    static_internal_ip  = optional(string)
  })
}

variable "artifact_registry_config" {
  description = "Artifact Registry Configuration"
  type = object({
    repository_id = string
    format        = string
  })
}

variable "iam_config" {
  description = "IAM Configuration"
  type = object({
    service_accounts = list(string)
  })
}

variable "labels" {
  description = "Common Labels"
  type        = map(string)
  default     = {}
}
