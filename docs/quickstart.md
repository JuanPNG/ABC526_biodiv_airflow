# Quickstart

This is the **short** operator/developer guide to build and run the platform end-to-end.

**Development order (bottom → top):**
1) Data plane: Beam pipelines → Flex Templates → Airflow DAG
2) Control plane: Terraform (bootstrap/ephemeral) → Cloud Build triggers → Workflows orchestration

**Production execution entrypoint:**
- Run the lifecycle via **Cloud Workflows** (recommended).
- Do not create/destroy Composer manually.

---

## Step 1 — Prerequisites

### Tools
You need:
- gcloud CLI
- Terraform
- Docker (or remote build equivalent)
- gsutil (included with gcloud)

Check:
```bash
gcloud version
terraform version
docker --version
gsutil version
```

### Auth
Use Application Default Credentials (ADC) for local development and testing:
```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
gcloud config set compute/region <REGION>
```

### Required Inputs (you will fill these in once)
Set these environment variables for copy/paste convenience:
```bash
export PROJECT_ID="<PROJECT_ID>"
export REGION="<REGION>"                # e.g. europe-west2
export TF_STATE_BUCKET="gs://<BUCKET>"  # terraform remote state bucket (no trailing slash)
export COMPOSER_ENV_NAME="<ENV_NAME>"   # ephemeral composer env name
export BRANCH_NAME="main"               # branch used by Cloud Build triggers
```

Repo layout (high level):
- `terraform/bootstrap`  → long-lived IAM + foundations
- `terraform/ephemeral`  → Composer environment only
- `terraform/cloudbuild.apply.yaml` / `terraform/cloudbuild.destroy.yaml` → apply/destroy triggers
- `workflows/biodiv_ephemeral.yaml` → Workflows lifecycle orchestrator
- `dags/` → Airflow DAG code
- `biodiv_airflow` → Modules needed for Airflow DAGs

> Note: Dataflow Flex Templates (container images + `flex_*.json` specs in GCS) are built in a separate repo.
> In this repo we assume the Flex Template JSON specs already exist under `gs://<bucket>/.../flex-templates/`.

## Step 2 — Develop & Validate the Airflow DAG Locally (then run in Composer)

This repo starts from the orchestration layer: an Airflow DAG that launches existing
Dataflow Flex Templates and writes `_SUCCESS` markers to GCS.

DAG ID:
```text
biodiv_pipelines_dag
```

### 2.1 Local dev setup (Airflow standalone)

```bash
export AIRFLOW_HOME="$(pwd)/.airflow"
airflow standalone
```

In another terminal:

```bash
airflow info | head
airflow dags list-import-errors
airflow dags list | grep biodiv_pipelines_dag
airflow tasks list biodiv_pipelines_dag
```

### 2.2 Required Airflow Variables (works locally and in Composer)

The DAG loads configuration at parse time via Airflow Variables. These must be set
both for local runs and for Composer runs.

```bash
# Core
airflow variables set biodiv_gcp_project "${PROJECT_ID}"
airflow variables set biodiv_gcp_region "${REGION}"
airflow variables set biodiv_bucket "<GCS_BUCKET_NAME_ONLY>"

# Flex template base path (GCS folder containing flex_*.json specs)
airflow variables set biodiv_flex_base "gs://<bucket>/biodiv-pipelines-dev/flex-templates"

# Output layout base (run artifacts written under .../runs/window_start=.../run_ts=...)
airflow variables set biodiv_output_base "gs://<bucket>/biodiv-pipelines-dev"

# Dataflow temp/staging
airflow variables set biodiv_df_temp_location "gs://<bucket>/biodiv-pipelines-dev/temp"
airflow variables set biodiv_df_staging_location "gs://<bucket>/biodiv-pipelines-dev/staging"

# SDK container image reference used by the Flex templates (must exist)
airflow variables set biodiv_sdk_container_image "<REGION>-docker.pkg.dev/<PROJECT_ID>/<AR_REPO>/<IMAGE>:<TAG>"

# Dataflow worker service account email (used by serviceAccountEmail in Dataflow environment)
airflow variables set biodiv_dataflow_worker_sa_email "dataflow-biodiv-worker@${PROJECT_ID}.iam.gserviceaccount.com"

# Elasticsearch inputs (used by taxonomy + provenance jobs)
airflow variables set elasticsearch_host "<https://...>"
airflow variables set elasticsearch_user "<user>"
airflow variables set elasticsearch_password "<password>"

# BigQuery dataset (must exist)
airflow variables set biodiv_bq_dataset "<DATASET>"
```

### 2.3 What the DAG validates

The first task `validate_config` fails fast if required variables are missing or defaulted,
before launching any Dataflow jobs.

### 2.4 Run tests locally (recommended)

Run a single task:

```bash
airflow tasks test biodiv_pipelines_dag validate_config 2026-01-29
```

Run the full DAG locally:

```bash
airflow dags test biodiv_pipelines_dag 2026-01-29
```

Verify artifacts exist in GCS:

```bash
gsutil ls "gs://<bucket>/biodiv-pipelines-dev/runs/window_start=2026-01-29/"
```

> Production runs are executed via Workflows + ephemeral Composer (see Step 5/6).

## Step 3 — Control Plane: Terraform Bootstrap (run locally)

Bootstrap is the long-lived foundation. It creates IAM, service accounts,
custom roles, and other shared resources.

> GCS buckets were created manually before running Terraform.

---

### 3.1 Create Required Buckets (manual)

#### A) Terraform Remote State Bucket

Create the bucket:

```bash
gsutil mb -p "${PROJECT_ID}" -l "${REGION}" gs://<TF_STATE_BUCKET>
```

⚠️ Important:
When configuring Terraform backend, you must use the **bucket name only**, without `gs://`.

Example:
- Bucket URI: `gs://my-tf-state-bucket`
- Terraform backend bucket value: `my-tf-state-bucket`

---

#### B) Pipeline Artifact Bucket (if separate)

If your pipeline outputs, flex templates, temp, and staging locations use a separate bucket:

```bash
gsutil mb -p "${PROJECT_ID}" -l "${REGION}" gs://<PIPELINE_BUCKET>
```

If you use a single bucket for everything, you can skip this.

---

### 3.2 Apply Bootstrap Stack

```bash
cd terraform/bootstrap

terraform init \
  -backend-config="bucket=<TF_STATE_BUCKET_NAME_ONLY>" \
  -backend-config="prefix=terraform/bootstrap"

terraform plan -out tfplan
terraform apply tfplan
```

Expected outcome:

- Service accounts created:
  - Composer runtime SA
  - Dataflow worker SA
  - Cloud Build lifecycle SA
  - Workflows SA
- Custom role(s) created (Composer lifecycle role)
- IAM bindings configured (least privilege)
- Permissions required by triggers and workflows established

Verify:

```bash
gcloud iam service-accounts list --project "${PROJECT_ID}"
```

---

### 3.3 Destroy Bootstrap (rare)

Bootstrap is long-lived and normally **not destroyed**.

If you need to fully tear down a dev project:

```bash
terraform destroy
```

## Step 4 — Control Plane: Terraform Ephemeral (Composer only, run locally)

The ephemeral stack provisions **only** the Cloud Composer 3 environment.

Composer is ephemeral.
The DAG bucket is permanent and already exists (created separately).

This step validates that Composer can be created and destroyed cleanly
before wiring Cloud Build and Workflows.

---

### 4.1 Apply Ephemeral Stack (create Composer)

```bash
cd terraform/ephemeral

terraform init \
  -backend-config="bucket=<TF_STATE_BUCKET_NAME_ONLY>" \
  -backend-config="prefix=terraform/ephemeral"

terraform plan -out tfplan
terraform apply tfplan
```

Wait until Composer reaches RUNNING:

```bash
gcloud composer environments describe "${COMPOSER_ENV_NAME}" \
  --location "${REGION}" \
  --project "${PROJECT_ID}" \
  --format="value(state)"
```

State must be:

```
RUNNING
```

---

### 4.2 Destroy Ephemeral Stack (delete Composer)

```bash
terraform destroy
```

Confirm deletion:

```bash
gcloud composer environments list \
  --locations "${REGION}" \
  --project "${PROJECT_ID}"
```

The environment should no longer appear.

## Step 5 — Automation: Create Cloud Build Triggers (UI)

Two Cloud Build triggers are required:

- **Apply trigger**: creates Composer (terraform apply) + syncs DAGs to permanent DAG bucket
- **Destroy trigger**: deletes Composer (terraform destroy)

These triggers must run using the **Cloud Build lifecycle service account** created in bootstrap.

---

### 5.1 Create Apply Trigger (UI)

Cloud Console → **Cloud Build** → **Triggers** → **Create trigger**

Fill in:

**Source**
- Repository: your repo
- Branch: `main` (or your chosen production branch)

**Configuration**
- Type: Cloud Build configuration file (YAML)
- Location: Repository
- Cloud Build config file: `cloudbuild.apply.yaml`

**Service account**
- Select the lifecycle Cloud Build SA created in bootstrap  
  (example: `cb-biodiv-composer-lifecycle@<PROJECT_ID>.iam.gserviceaccount.com`)

**Substitutions**
Add required substitutions used by your build config, typically:

- `_PROJECT_ID = <PROJECT_ID>`
- `_REGION = <REGION>`
- `_COMPOSER_ENV_NAME = <ENV_NAME>`
- `_TF_STATE_BUCKET = <TF_STATE_BUCKET_NAME_ONLY>`   (no `gs://`)
- `_DAG_BUCKET = <DAG_BUCKET_NAME_ONLY>`             (permanent DAG bucket)
- `_BRANCH_NAME = main`

Save the trigger and copy the trigger ID.
You will pass this ID into Workflows later.

---

### 5.2 Create Destroy Trigger (UI)

Cloud Console → **Cloud Build** → **Triggers** → **Create trigger**

Fill in:

**Source**
- Same repo / branch

**Configuration**
- Cloud Build config file: `cloudbuild.destroy.yaml`

**Service account**
- Same lifecycle Cloud Build SA as Apply trigger

**Substitutions**
Use the same substitutions as Apply trigger (at least the Terraform backend inputs):

- `_PROJECT_ID`
- `_REGION`
- `_COMPOSER_ENV_NAME`
- `_TF_STATE_BUCKET`
- `_BRANCH_NAME`

Save the trigger and copy the trigger ID.

---

### 5.3 Test triggers manually (CLI)

You can run triggers on demand to validate they work before wiring Workflows:

```bash
# Run apply trigger
gcloud builds triggers run <APPLY_TRIGGER_ID> \
  --branch="${BRANCH_NAME}" \
  --project="${PROJECT_ID}"

# Run destroy trigger
gcloud builds triggers run <DESTROY_TRIGGER_ID> \
  --branch="${BRANCH_NAME}" \
  --project="${PROJECT_ID}"
```

Watch builds:

```bash
gcloud builds list --project "${PROJECT_ID}" --limit=5
```

Open the most recent build logs in Cloud Console if a build fails.

---

### 5.4 Expected behavior

Apply trigger should:
- Run `terraform apply` for `terraform/ephemeral`
- Sync DAG code to the **permanent DAG bucket** deterministically (`gsutil rsync -d`)

Destroy trigger should:
- Run `terraform destroy` for `terraform/ephemeral`

Bootstrap is never touched by triggers.

## Step 6 — Orchestration: Deploy and Execute the Workflow

Workflows is the single entrypoint for production-style runs:
it creates Composer, waits for readiness, triggers the Airflow DAG, waits for completion,
then destroys Composer (best-effort).

Workflow name:
```text
biodiv_ephemeral_lifecycle
```

---

### 6.1 Deploy the Workflow

```bash
gcloud workflows deploy biodiv_ephemeral_lifecycle \
  --source=biodiv_ephemeral.yaml \
  --location="${REGION}" \
  --project="${PROJECT_ID}"
```

Verify it exists:

```bash
gcloud workflows describe biodiv_ephemeral_lifecycle \
  --location="${REGION}" \
  --project="${PROJECT_ID}"
```

---

### 6.2 Execute the Full Lifecycle

Run the workflow with the required inputs:

```bash
gcloud workflows execute biodiv_ephemeral_lifecycle \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --data='{
    "project_id": "'"${PROJECT_ID}"'",
    "region": "'"${REGION}"'",
    "composer_env_name": "'"${COMPOSER_ENV_NAME}"'",
    "apply_trigger_id": "<APPLY_TRIGGER_ID>",
    "destroy_trigger_id": "<DESTROY_TRIGGER_ID>",
    "branch_name": "'"${BRANCH_NAME}"'",
    "dag_id": "biodiv_pipelines_dag"
  }'
```

If your workflow supports passing a DAG conf payload, add it (optional):

```json
"dag_conf": {
  "example_key": "example_value"
}
```

---

### 6.3 Watch Execution

List recent executions:

```bash
gcloud workflows executions list \
  --workflow=biodiv_ephemeral_lifecycle \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --limit=5
```

Describe one execution:

```bash
gcloud workflows executions describe <EXECUTION_ID> \
  --workflow=biodiv_ephemeral_lifecycle \
  --location="${REGION}" \
  --project="${PROJECT_ID}"
```

---

### 6.4 What “success” means

A successful execution means:

1. Cloud Build apply succeeded (Composer created + DAGs synced)
2. Composer reached RUNNING
3. Airflow DAG run finished in SUCCESS
4. Cloud Build destroy was triggered (best-effort)
5. Workflow returned SUCCESS

---

### 6.5 Where to look when something fails (fast triage)

If the workflow fails, determine which phase failed:

**A) Cloud Build apply/destroy failed**
- Cloud Console → Cloud Build → History
- Or via CLI:
```bash
gcloud builds list --project "${PROJECT_ID}" --limit=10
```

**B) Composer did not reach RUNNING**
- Cloud Console → Composer → Environments
- Or:
```bash
gcloud composer environments describe "${COMPOSER_ENV_NAME}" \
  --location "${REGION}" --project "${PROJECT_ID}"
```

**C) DAG failed**
- Open Airflow UI (Composer)
- Check task logs for the failing Dataflow operator
- Also check Dataflow job logs in Cloud Logging

---

### 6.6 Verify Outputs (GCS)

Pipeline artifacts are written under your pipeline bucket output base (example layout):

```bash
gsutil ls "gs://<PIPELINE_BUCKET>/biodiv-pipelines-dev/runs/"
```

Look for a run partition:

```bash
gsutil ls "gs://<PIPELINE_BUCKET>/biodiv-pipelines-dev/runs/window_start=*/run_ts=*/"
```

Stage-level `_SUCCESS` markers indicate completion per pipeline stage.

---

### 6.7 Re-run / cleanup

If a run fails:
- Re-run the workflow (it creates a new run partition)
- If destroy failed and Composer remains:
  - Run destroy trigger manually:
```bash
gcloud builds triggers run <DESTROY_TRIGGER_ID> \
  --branch="${BRANCH_NAME}" \
  --project="${PROJECT_ID}"
```