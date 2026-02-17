/**
 * Ephemeral stack: ONLY the Composer environment resource.
 * - No API enablement
 * - No service account creation
 * - No IAM bindings
 */

locals {
  composer_env_sa_email = "${var.composer_env_sa_account_id}@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_composer_environment" "env" {
  provider = google-beta
  name     = var.env_name
  region   = var.region
  project  = var.project_id

  storage_config {
    bucket = "gs://${var.composer_env_bucket_name}"
  }

  config {
    environment_size = var.composer_environment_size

    software_config {
      image_version = var.image_version

      env_variables = merge(
        {
          AIRFLOW_VAR_BIODIV_GCP_PROJECT = var.project_id
          AIRFLOW_VAR_BIODIV_GCP_REGION  = var.region
          AIRFLOW_VAR_BIODIV_BUCKET      = var.gcs_bucket_name
        },
        var.airflow_env_vars
      )

      airflow_config_overrides = {
        "secrets-backend" = "airflow.providers.google.cloud.secrets.secret_manager.CloudSecretManagerBackend"

        "secrets-backend-kwargs" = jsonencode({
          variables_prefix   = "gbdp"
          connections_prefix = "airflow-connections"
          sep                = "_"
        })
      }
    }

    node_config {
      service_account = local.composer_env_sa_email
    }
  }
}
