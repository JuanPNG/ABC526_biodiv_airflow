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

  # Persist DAGs across recreate (your current approach)
  storage_config {
    bucket = "gs://${var.composer_env_bucket_name}"
  }

  config {
    environment_size = var.composer_environment_size

    software_config {
      image_version = var.image_version
    }

    node_config {
      service_account = local.composer_env_sa_email
    }
  }
}
