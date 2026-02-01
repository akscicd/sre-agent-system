variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "network_name" {
  description = "The name of the VPC network"
  type        = string
}

variable "subnet_name" {
  description = "The name of the subnetwork"
  type        = string
}

variable "subnet_cidr" {
  description = "The IP CIDR range for the subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "target_tags" {
  description = "List of tags to apply firewall rules to"
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "A map of labels to apply to resources"
  type        = map(string)
  default     = {}
}

variable "jenkins_vm_static_ip" {
  description = "Static internal IP address of the Jenkins master VM"
  type        = string
  default     = null
}

variable "agent_vm_static_ip" {
  description = "Static internal IP address of the Jenkins agent VM"
  type        = string
  default     = null
}
