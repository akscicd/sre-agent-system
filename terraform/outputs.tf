output "jenkins_ip" {
  value       = google_compute_instance.jenkins_vm.network_interface.0.access_config.0.nat_ip
  description = "Public IP of the Jenkins Server"
}

output "artifact_registry_repo" {
  value = google_artifact_registry_repository.repo.id
}
