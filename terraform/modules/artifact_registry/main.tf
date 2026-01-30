terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_artifact_registry_repository" "repo" {
  location      = var.location
  repository_id = var.repository_id
  format        = var.format
  project       = var.project_id
  
  labels = var.labels
}
