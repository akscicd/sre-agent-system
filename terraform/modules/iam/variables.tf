variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "service_accounts" {
  description = "List of Service Account names to create"
  type        = set(string)
  default     = []
}
