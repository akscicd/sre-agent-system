terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.51.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = "us-central1"
}

# --- 1. Networking ---
resource "google_compute_network" "vpc" {
  name                    = "sre-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "sre-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = "us-central1"
  network       = google_compute_network.vpc.id
}

# Allow SSH via IAP (Identity-Aware Proxy)
resource "google_compute_firewall" "allow_ssh_iap" {
  name    = "allow-ssh-iap"
  network = google_compute_network.vpc.id
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["35.235.240.0/20"] # IAP IP range
}

# Allow access to Jenkins (Port 8080)
resource "google_compute_firewall" "allow_jenkins" {
  name    = "allow-jenkins"
  network = google_compute_network.vpc.id
  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
  source_ranges = ["0.0.0.0/0"] # Open to world for demo - RESTRICT IN PROD
}

# --- 2. Identity ---
# Jenkins Builder Identity
resource "google_service_account" "jenkins_sa" {
  account_id   = "jenkins-builder"
  display_name = "Jenkins CI/CD Service Account"
}

# Agent Runtime Identity
resource "google_service_account" "agent_sa" {
  account_id   = "sre-agent-runtime"
  display_name = "SRE Agent Runtime Service Account"
}

# Grant Jenkins permission to Push Images & Deploy
resource "google_project_iam_member" "jenkins_permissions" {
  for_each = toset([
    "roles/artifactregistry.writer",
    "roles/run.admin",
    "roles/iam.serviceAccountUser", # To act as agent_sa
    "roles/storage.objectViewer"
  ])
  role    = each.key
  member  = "serviceAccount:${google_service_account.jenkins_sa.email}"
  project = var.project_id
}

# Grant Agent Runtime Permissions (Least Privilege)
resource "google_project_iam_member" "agent_permissions" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/compute.admin",       # To manage VMs
    "roles/container.developer", # To manage GKE
    "roles/aiplatform.user",     # To use Vertex AI
    "roles/secretmanager.secretAccessor"
  ])
  role    = each.key
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
  project = var.project_id
}

# --- 3. Artifact Registry ---
resource "google_artifact_registry_repository" "repo" {
  location      = "us-central1"
  repository_id = "sre-agent-repo"
  format        = "DOCKER"
}

# --- 4. Jenkins VM ---
resource "google_compute_instance" "jenkins_vm" {
  name         = "jenkins-server"
  machine_type = "e2-standard-2"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 50
    }
  }

  network_interface {
    network    = google_compute_network.vpc.id
    subnetwork = google_compute_subnetwork.subnet.id
    access_config {} # Ephemeral Public IP
  }

  service_account {
    email  = google_service_account.jenkins_sa.email
    scopes = ["cloud-platform"]
  }

  tags = ["jenkins-server"]

  metadata_startup_script = <<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y openjdk-17-jre docker.io
    
    # Install Jenkins
    curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null
    echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/ | tee /etc/apt/sources.list.d/jenkins.list > /dev/null
    apt-get update
    apt-get install -y jenkins
    
    # Configure Permissions
    usermod -aG docker jenkins
    chmod 666 /var/run/docker.sock
    
    # Install gcloud
    snap install google-cloud-cli --classic
    
    systemctl enable jenkins
    systemctl start jenkins
  EOF
}
