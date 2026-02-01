terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_compute_network" "vpc" {
  name                    = var.network_name
  auto_create_subnetworks = false
  project                 = var.project_id
}

resource "google_compute_subnetwork" "subnet" {
  name                     = var.subnet_name
  ip_cidr_range            = var.subnet_cidr
  region                   = var.region
  network                  = google_compute_network.vpc.id
  project                  = var.project_id
  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  name    = "${var.network_name}-router"
  network = google_compute_network.vpc.id
  region  = var.region
  project = var.project_id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.network_name}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  project                            = var.project_id
}


resource "google_compute_firewall" "allow_iap" {
  name    = "${var.network_name}-allow-iap"
  network = google_compute_network.vpc.id
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["22", "8080"]
  }

  source_ranges = compact([
    "35.235.240.0/20",
    var.jenkins_vm_static_ip != null ? "${var.jenkins_vm_static_ip}/32" : null,
    var.agent_vm_static_ip != null ? "${var.agent_vm_static_ip}/32" : null,
  ])
  target_tags = var.target_tags
}
