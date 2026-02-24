############################################
# Enable Required APIs
############################################

resource "google_project_service" "composer_api" {
  provider = google-beta
  project  = var.project_id
  service  = "composer.googleapis.com"

  disable_on_destroy = false
  check_if_service_has_usage_on_destroy = true
}

############################################
# Composer Environment Service Account
############################################

resource "google_service_account" "composer_env_sa" {
  provider     = google-beta
  account_id   = var.composer_env_sa_account_id
  display_name = "Composer env SA for ${var.env_name}"
}
