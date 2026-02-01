module "iam" {
  source           = "../../modules/iam"
  project_id       = var.project_id
  service_accounts = var.iam_config.service_accounts
}

resource "google_project_iam_member" "jenkins_permissions" {
  for_each = toset([
    "roles/artifactregistry.writer",
    "roles/run.admin",
    "roles/iam.serviceAccountUser",
    "roles/storage.objectViewer"
  ])
  role    = each.key
  member  = "serviceAccount:${module.iam.service_accounts["jenkins-sa"]}"
  project = var.project_id
}

resource "google_project_iam_member" "agent_permissions" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/compute.admin",
    "roles/container.developer",
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor"
  ])
  role    = each.key
  member  = "serviceAccount:${module.iam.service_accounts["sre-agent-runtime"]}"
  project = var.project_id
}


module "networking" {
  source     = "../../modules/networking"
  project_id = var.project_id
  region     = var.region

  network_name = var.network_config.vpc_name
  subnet_name  = var.network_config.subnet_name
  subnet_cidr  = var.network_config.subnet_cidr

  target_tags = ["jenkins"]

  labels = var.labels

  jenkins_vm_static_ip = var.jenkins_config.static_internal_ip
  agent_vm_static_ip   = var.agent_config.static_internal_ip
}


module "artifact_registry" {
  source     = "../../modules/artifact_registry"
  project_id = var.project_id
  location   = var.region

  repository_id = var.artifact_registry_config.repository_id
  format        = var.artifact_registry_config.format

  labels = var.labels
}


module "jenkins_vm" {
  source     = "../../modules/compute"
  project_id = var.project_id
  zone       = var.zone

  vm_name             = var.jenkins_config.vm_name
  instance_type       = var.jenkins_config.machine_type
  deletion_protection = var.jenkins_config.deletion_protection
  tags                = var.jenkins_config.tags
  boot_disk_image     = var.jenkins_config.boot_image
  boot_disk_size      = var.jenkins_config.boot_size
  static_internal_ip  = var.jenkins_config.static_internal_ip

  service_account_email = module.iam.service_accounts["jenkins-sa"]

  network_name = module.networking.network_name
  subnet_name  = module.networking.subnet_name

  metadata_startup_script = file("${path.module}/scripts/install_jenkins.sh")

  labels = var.labels
}


module "agent_vm" {
  source     = "../../modules/compute"
  project_id = var.project_id
  zone       = var.zone

  vm_name             = var.agent_config.vm_name
  instance_type       = var.agent_config.machine_type
  deletion_protection = var.agent_config.deletion_protection
  tags                = var.agent_config.tags
  boot_disk_image     = var.agent_config.boot_image
  boot_disk_size      = var.agent_config.boot_size
  static_internal_ip  = var.agent_config.static_internal_ip

  service_account_email = module.iam.service_accounts["jenkins-sa"]

  network_name = module.networking.network_name
  subnet_name  = module.networking.subnet_name

  metadata_startup_script = file("${path.module}/scripts/jenkins_agent_setup.sh")

  labels = var.labels
}
