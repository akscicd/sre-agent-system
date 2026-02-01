variable "project_id" {
  type = string
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "instance_type" {
  type = string
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "vm_name" {
  description = "The specific name of the VM"
  type        = string
}

variable "network_name" {
  type = string
}

variable "subnet_name" {
  type = string
}

variable "service_account_email" {
  description = "The email of the Service Account to attach"
  type        = string
}

variable "metadata_startup_script" {
  description = "Startup script metadata (Optional)"
  type        = string
  default     = null # Allowing null for cleaner conditional logic if needed, typically "" works too but null is more explicit for 'optional'
}

variable "boot_disk_image" {
  description = "Boot disk image"
  type        = string
  default     = "projects/sre-agent-prod/global/images/akscicd-jenkins-server"
}

variable "boot_disk_size" {
  description = "Boot disk size in GB"
  type        = number
  default     = 50
}

variable "tags" {
  description = "Network tags for the instance"
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "A map of labels to apply to resources"
  type        = map(string)
  default     = {}
}

variable "static_internal_ip" {
  description = "Static internal IP address"
  type        = string
  default     = null
}
