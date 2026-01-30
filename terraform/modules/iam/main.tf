terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_service_account" "sa" {
  for_each     = var.service_accounts
  account_id   = each.key
  display_name = "Service Account: ${each.key}"
  project      = var.project_id
}
