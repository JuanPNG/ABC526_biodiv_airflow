/**
 * Ephemeral stack outputs:
 * - used by Workflows / automation to find Airflow URI and DAG bucket
 * - useful for debugging and job orchestration
 */

output "composer_env_name" {
  description = "Composer environment name (resource name)."
  value       = google_composer_environment.env.name
}

output "airflow_uri" {
  description = "Airflow Web UI base URI (also used for Airflow REST API calls)."
  value       = google_composer_environment.env.config[0].airflow_uri
}

output "dag_gcs_prefix" {
  description = "GCS prefix for DAGs in this Composer environment bucket."
  value       = google_composer_environment.env.config[0].dag_gcs_prefix
}
