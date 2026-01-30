variable "project_id" {
  type = string
}

variable "location" {
  type    = string
  default = "us-central1"
}

variable "repository_id" {
  description = "The repository ID"
  type        = string
  default     = "sre-agent-repo"
}

variable "format" {
  description = "The format of the repository (DOCKER, MAVEN, NPM, etc.)"
  type        = string
  default     = "DOCKER"
}

variable "labels" {
  description = "A map of labels to apply to resources"
  type        = map(string)
  default     = {}
}
