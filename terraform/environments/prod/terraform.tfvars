project_id = "sre-agent-prod"
region     = "us-central1"
zone       = "us-central1-a"


network_config = {
  vpc_name    = "akscicd-vpc-prod"
  subnet_name = "akscicd-subnet-prod"
  subnet_cidr = "10.0.0.0/24"
}


compute_config = {
  jenkins_vm_name     = "jenkins-server"
  machine_type        = "e2-standard-4"
  deletion_protection = true
  tags                = ["akscicd-vm", "jenkins"]
  boot_image          = "ubuntu-os-cloud/ubuntu-2204-lts"
  boot_size           = 50
}


iam_config = {
  service_accounts = [
    "jenkins-sa", 
    "sre-agent-runtime"
  ]
}


artifact_registry_config = {
  repository_id = "sre-agent-repo"
  format        = "DOCKER"
}


labels = {
  environment = "prod"
  managed_by  = "terraform"
  team        = "devops"
  cost_center = "sre-platform"
}
