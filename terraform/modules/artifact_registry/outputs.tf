output "repository_name" {
  value = google_artifact_registry_repository.repo.name
}

output "repository_url" {
  value = "${var.location}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}
