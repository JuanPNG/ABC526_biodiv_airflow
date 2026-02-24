/**
 * Outputs are useful for debugging and for wiring into other automation (Workflows, scripts).
 */


output "composer_env_sa_email" {
  value       = google_service_account.composer_env_sa.email
  description = "Service account email used by Composer environment workloads."
}

output "dataflow_worker_sa_email" {
  value       = google_service_account.dataflow_worker_sa.email
  description = "Service account email used by Dataflow workers."
}

output "cloudbuild_sa_email" {
  value       = google_service_account.cloudbuild_lifecycle_sa.email
  description = "Service account email used by Cloud Build triggers."
}

output "workflows_sa_email" {
  value       = google_service_account.workflows_lifecycle_sa.email
  description = "Service account email used by Workflows execution."
}