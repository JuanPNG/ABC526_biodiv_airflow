
/**
 * Terraform + provider version pinning and remote state configuration.
 *
 * - Pin provider versions for reproducible deployments.
 * - Store state remotely (GCS backend) so teams can collaborate safely.
 */
terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.39.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.39.0"
    }
  }

  # Remote state in GCS (bucket is injected at terraform init time).
  backend "gcs" {
    prefix = "composer/bootstrap/biodiversity-pipelines"
  }
}
