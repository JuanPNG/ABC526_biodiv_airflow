/**
 * Global / environment-level configuration
 * Best practice: keep environment-specific identifiers OUT of defaults.
 */

variable "project_id" {
  type        = string
  description = "GCP project ID where the Composer environment and IAM resources are created."
}

variable "region" {
  type        = string
  description = "GCP region for the Composer environment."
  default     = "europe-west2"
}

variable "env_name" {
  type        = string
  description = "Fixed name of the Cloud Composer environment."
  default     = "biodiversity-pipelines-composer-env"
}

variable "image_version" {
  type        = string
  description = "Pinned Cloud Composer 3 image version (avoid using 'latest')."
  default     = "composer-3-airflow-2.10.5-build.25"
}

variable "composer_env_sa_account_id" {
  type        = string
  description = "Service account ID used by the Composer environment workloads (scheduler, workers, webserver)."
  default     = "composer-biodiv-ephemeral"
}

# --------------------------------------------------------------------
# Dataflow configuration (best practice: dedicated worker service account)
# --------------------------------------------------------------------

variable "dataflow_worker_sa_account_id" {
  type        = string
  description = "Service account ID used by Dataflow workers (Beam pipelines)."
  default     = "dataflow-biodiv-worker"
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
  description = "Persistent custom environment bucket for Composer (contains dags/, logs/, plugins/, data/)."
}

# --------------------------------------------------------------------
# BigQuery access configuration
# --------------------------------------------------------------------

variable "bq_datasets" {
  type        = list(string)
  description = "BigQuery dataset IDs (dataset name only) that Dataflow workers can write to."
}

# --------------------------------------------------------------------
# Artifact Registry access configuration
# --------------------------------------------------------------------

variable "artifact_registry_repo_names" {
  type        = list(string)
  description = "Artifact Registry repository names that store Dataflow Flex Template images."
}

variable "artifact_registry_location" {
  type        = string
  description = "Region where the Artifact Registry repositories are located."
  default     = "europe-west2"
}

# --------------------------------------------------------------------
# Optional services
# --------------------------------------------------------------------

variable "enable_secret_manager" {
  type        = bool
  description = "Grant Secret Manager access to Composer/Dataflow service accounts."
  default     = false
}
