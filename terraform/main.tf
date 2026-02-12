/**
 * Cloud Composer 3 environment definition.
 *
 * This file is responsible ONLY for:
 * - Enabling the Composer API
 * - Creating a dedicated service account for the Composer environment
 * - Creating the Composer environment itself
 *
 * It deliberately does NOT:
 * - Manage the Composer GCS bucket (Composer owns it)
 * - Grant Dataflow / BigQuery / Storage permissions (handled in iam.tf)
 *
 * This separation keeps the environment definition easy to review
 * and reduces the risk of accidental permission changes.
 */

# ------------------------------------------------------------
# Enable required API
# ------------------------------------------------------------

resource "google_project_service" "composer_api" {
  provider = google-beta
  project  = var.project_id
  service  = "composer.googleapis.com"

  # Keep the API enabled even if the environment is destroyed.
  disable_on_destroy = false

  # Safety guard in shared projects.
  check_if_service_has_usage_on_destroy = true
}

# ------------------------------------------------------------
# Composer Environment Service Account (custom, best practice)
# ------------------------------------------------------------

/**
 * Dedicated service account used by Composer components
 * (scheduler, webserver, workers).
 *
 * Best practice:
 * - Do NOT use the default Compute Engine service account
 * - Use a custom SA with least privilege
 */
resource "google_service_account" "composer_env_sa" {
  provider     = google-beta
  account_id   = var.composer_env_sa_account_id
  display_name = "Composer env SA for ${var.env_name}"
}

# ------------------------------------------------------------
# Minimum IAM required for Composer environment to function
# ------------------------------------------------------------

/**
 * roles/composer.worker is required when using a custom
 * service account for the Composer environment.
 *
 * This role allows Composer to manage its internal workloads.
 */
resource "google_project_iam_member" "composer_worker_role" {
  provider = google-beta
  project  = var.project_id
  role     = "roles/composer.worker"
  member   = "serviceAccount:${google_service_account.composer_env_sa.email}"
}

# ------------------------------------------------------------
# Composer 3 Environment
# ------------------------------------------------------------

/**
 * Cloud Composer 3 environment.
 *
 * Key best-practice choices:
 * - Explicit image_version (no "latest")
 * - Custom service account
 * - Public IP (as requested)
 */
resource "google_composer_environment" "env" {
  provider = google-beta
  name     = var.env_name

  depends_on = [
    google_project_service.composer_api,
    google_project_iam_member.composer_worker_role,
  ]

  # Persist DAGs across recreate
  storage_config {
    bucket = "gs://${var.composer_env_bucket_name}"
  }

  config {
    software_config {
      # Composer 3 requires an explicit image version
      image_version = var.image_version
    }

    node_config {
      # Run all Composer workloads as the custom service account
      service_account = google_service_account.composer_env_sa.email
    }
  }
}
