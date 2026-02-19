/**
 * IAM for Composer (Airflow) and Dataflow (Beam) using least privilege.
 *
 * This version assumes the GCS bucket is DEDICATED to this workload (no shared
 * production data). Therefore we use clean, auditable bucket-level IAM and do
 * NOT use prefix-restricted IAM Conditions.
 *
 * Identities:
 * - Composer environment SA: control plane (submits Dataflow jobs, may write/read markers).
 * - Dataflow worker SA: data plane (reads/writes GCS, writes BigQuery, pulls images).
 */

# Dedicated Dataflow worker service account (recommended).
resource "google_service_account" "dataflow_worker_sa" {
  account_id   = var.dataflow_worker_sa_account_id
  display_name = "Dataflow worker SA for ${var.env_name}"
}

locals {
  composer_sa = google_service_account.composer_env_sa.email
  dataflow_sa = google_service_account.dataflow_worker_sa.email
}

# -----------------------------
# Composer SA (control plane)
# -----------------------------

# Submit Flex Template jobs.
resource "google_project_iam_member" "composer_dataflow_developer" {
  project = var.project_id
  role    = "roles/dataflow.developer"
  member  = "serviceAccount:${local.composer_sa}"
}

# BigQuery job execution (queries/load jobs triggered by tasks/operators).
resource "google_project_iam_member" "composer_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${local.composer_sa}"
}

# GCS: Composer writes _SUCCESS markers and may read them later.
# Dedicated bucket => simple bucket-level object permissions.
resource "google_storage_bucket_iam_member" "composer_bucket_object_admin" {
  bucket = var.gcs_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.composer_sa}"
}

# Composer environment bucket (DAGs / logs / plugins)
resource "google_storage_bucket_iam_member" "composer_env_bucket_object_admin" {
  bucket = var.composer_env_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.composer_sa}"
}

# Pull container images (repo-scoped).
resource "google_artifact_registry_repository_iam_member" "composer_ar_reader" {
  for_each   = toset(var.artifact_registry_repo_names)
  project    = var.project_id
  location   = var.artifact_registry_location
  repository = each.value
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${local.composer_sa}"
}

# Optional: read secrets (preferred over storing secrets as Airflow Variables).
resource "google_project_iam_member" "composer_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.composer_sa}"
}

# -----------------------------
# Dataflow worker SA (data plane)
# -----------------------------

# GCS: Dataflow needs staging/temp/output object read/write in the dedicated bucket.
resource "google_storage_bucket_iam_member" "dataflow_bucket_object_admin" {
  bucket = var.gcs_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.dataflow_sa}"
}

# GCS: Dataflow also performs bucket metadata checks (e.g., storage.buckets.get).
# This avoids 403 on GET bucket during staging/temp validation.
resource "google_storage_bucket_iam_member" "dataflow_bucket_viewer" {
  bucket = var.gcs_bucket_name
  role   = "roles/storage.bucketViewer"
  member = "serviceAccount:${local.dataflow_sa}"
}

# BigQuery job execution (some sinks use load jobs).
resource "google_project_iam_member" "dataflow_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${local.dataflow_sa}"
}

# BigQuery dataset access using dataset access entries (future-proof for authorized views).
resource "google_bigquery_dataset_access" "dataflow_bq_data_editor_access" {
  for_each   = toset(var.bq_datasets)
  project    = var.project_id
  dataset_id = each.value

  role          = "roles/bigquery.dataEditor"
  user_by_email = local.dataflow_sa
}

# Workers must pull the SDK container image from Artifact Registry.
resource "google_artifact_registry_repository_iam_member" "dataflow_ar_reader" {
  for_each   = toset(var.artifact_registry_repo_names)
  project    = var.project_id
  location   = var.artifact_registry_location
  repository = each.value
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${local.dataflow_sa}"
}

resource "google_project_iam_member" "dataflow_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.dataflow_sa}"
}

# Allow the Composer environment service account to "actAs" the Dataflow worker SA.
# Required when you set environment.serviceAccountEmail in the Dataflow Flex Template launch request.
resource "google_service_account_iam_member" "composer_can_act_as_dataflow_worker" {
  service_account_id = google_service_account.dataflow_worker_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${local.composer_sa}"
}

# Allow “Dataflow worker” permissions (work item lease/commit/shuffle APIs)
resource "google_project_iam_member" "dataflow_worker_role" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${local.dataflow_sa}"
}

# Cloud build account and permissions to use Cloud Composer
resource "google_service_account" "cloudbuild_lifecycle_sa" {
  provider     = google-beta
  project      = var.project_id
  account_id   = var.cloudbuild_sa_account_id
  display_name = "Cloud Build SA for Biodiv Composer lifecycle"
}

# Permissions to add logs
resource "google_project_iam_member" "cloudbuild_logs_writer" {
  provider = google-beta
  project  = var.project_id
  role     = "roles/logging.logWriter"
  member   = "serviceAccount:${google_service_account.cloudbuild_lifecycle_sa.email}"
}

# Permission to actAs composer runtime SA
resource "google_service_account_iam_member" "cloudbuild_can_act_as_composer_runtime_sa" {
  provider           = google-beta
  service_account_id = google_service_account.composer_env_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloudbuild_lifecycle_sa.email}"
}

# Wrokflows account
resource "google_service_account" "workflows_lifecycle_sa" {
  project      = var.project_id
  account_id   = var.workflows_sa_name
  display_name = "Workflows SA for Biodiv Composer lifecycle"
}

resource "google_project_iam_member" "workflows_cloudbuild_builds_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.workflows_lifecycle_sa.email}"
}

resource "google_project_iam_member" "workflows_composer_user" {
  project = var.project_id
  role    = "roles/composer.user"
  member  = "serviceAccount:${google_service_account.workflows_lifecycle_sa.email}"
}

resource "google_project_iam_member" "workflows_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.workflows_lifecycle_sa.email}"
}

