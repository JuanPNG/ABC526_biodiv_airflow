/**
 * Provider configuration.
 * Uses both google and google-beta providers. Composer fields often land in google-beta first.
 */
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
