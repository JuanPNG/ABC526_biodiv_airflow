#--------------------------------------------------------------------
# Global / environment-level configuration
#--------------------------------------------------------------------

variable "project_id" {
  type        = string
  description = "GCP project ID where the Composer environment and IAM resources are created."
}

variable "region" {
  type        = string
  description = "GCP region for the Composer environment."
}

variable "env_name" {
  type        = string
  description = "Fixed name of the Cloud Composer environment."
}

variable "image_version" {
  type        = string
  description = "Pinned Cloud Composer 3 image version (avoid using 'latest')."
}

variable "composer_env_sa_account_id" {
  type        = string
  description = "Service account ID used by the Composer environment workloads (scheduler, workers, webserver)."
}

variable "composer_environment_size" {
  type        = string
  description = "Composer environment size tier. Controls core infrastructure sizing (including the Airflow database)."
  default = "ENVIRONMENT_SIZE_SMALL"

  validation {
    condition = contains(
      ["ENVIRONMENT_SIZE_SMALL", "ENVIRONMENT_SIZE_MEDIUM", "ENVIRONMENT_SIZE_LARGE"],
      var.composer_environment_size
    )
    error_message = "composer_environment_size must be one of ENVIRONMENT_SIZE_SMALL, ENVIRONMENT_SIZE_MEDIUM, ENVIRONMENT_SIZE_LARGE."
  }
}

# --------------------------------------------------------------------
# Cloud Storage (GCS) configuration
# --------------------------------------------------------------------

variable "gcs_bucket_name" {
  type        = string
  description = "Pipeline data bucket (Dataflow temp/staging/output)."
}

variable "composer_env_bucket_name" {
  type        = string
  description = "Persistent custom environment bucket for Composer (contains dags/)."
}

# --------------------------------------------------------------------
# Airflow vars
# --------------------------------------------------------------------

variable "airflow_env_vars" {
  description = "Non-sensitive env vars to inject into Airflow. Use AIRFLOW_VAR_* to back Airflow Variables."
  type        = map(string)
  default     = {}
}
