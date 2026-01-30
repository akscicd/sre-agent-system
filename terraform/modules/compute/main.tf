terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_compute_instance" "vm" {
  name                = var.vm_name
  machine_type        = var.instance_type
  zone                = var.zone
  project             = var.project_id
  deletion_protection = var.deletion_protection

  boot_disk {
    initialize_params {
      image = var.boot_disk_image
      size  = var.boot_disk_size
    }
  }

  network_interface {
    network    = var.network_name
    subnetwork = var.subnet_name
  }

  service_account {
    email  = var.service_account_email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  tags = var.tags
  
  labels = var.labels

  metadata_startup_script = var.metadata_startup_script
}
