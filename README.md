# Biodiversity Ephemeral Composer Platform

This repository contains the orchestration layer for running biodiversity
Dataflow Flex Template pipelines using an **ephemeral Cloud Composer 3 environment**.

The system:

1. Creates Composer via Terraform (ephemeral stack)
2. Syncs DAGs to a permanent DAG bucket
3. Triggers an Airflow DAG
4. Waits for completion
5. Destroys Composer

Execution is fully automated via **Cloud Workflows**.

---

## What This Repo Assumes

The following already exist:

- Dataflow Flex Templates (built in a separate repo)
- Artifact Registry repository
- Pipeline artifact bucket
- Permanent DAG bucket
- Terraform remote state bucket
- Required IAM (via bootstrap stack)

See `docs/quickstart.md` for full setup from scratch.

---

## Production Entry Point

The system is executed via Workflows:

```bash
gcloud workflows execute biodiv_ephemeral_lifecycle \
  --location="<REGION>" \
  --project="<PROJECT_ID>" \
  --data='{
    "project_id": "<PROJECT_ID>",
    "region": "<REGION>",
    "composer_env_name": "<ENV_NAME>",
    "apply_trigger_id": "<APPLY_TRIGGER_ID>",
    "destroy_trigger_id": "<DESTROY_TRIGGER_ID>",
    "branch_name": "main",
    "dag_id": "biodiv_pipelines_dag"
  }'
```

This will:

- Create Composer
- Run the DAG
- Destroy Composer

---

## Main Components

- `terraform/bootstrap/` → long-lived IAM + foundations
- `terraform/ephemeral/` → Composer environment only
- `cloudbuild.apply.yaml` → apply + DAG sync
- `cloudbuild.destroy.yaml` → destroy Composer
- `biodiv_ephemeral.yaml` → lifecycle orchestration
- `dags/` → Airflow DAG code

---

## Documentation

- `docs/quickstart.md` → How to set up and run everything
- `docs/architecture.md` → Full design and IAM documentation





TO DELETE:

# Biodiv Pipelines DAG (Airflow / Cloud Composer). How to Run

This DAG (`biodiv_ingestion`) orchestrates two Dataflow Flex Template pipelines in Google Cloud Composer:

1) taxonomy  
2) occurrences  
3) cleaning_occs  
4) spatial_annotation  
5) range_estimation  
6) data_provenance 

The primary DAG is: **`biodiv_pipelines_dag`** (file: `dags/biodiv_pipelines_dag.py`).

The DAG is designed for **Cloud Composer 3** (Airflow 2.10.x), but can be developed and tested locally.

It uses **Terraform** to create an **ephemeral** Cloud Composer 3 environment with **least-privilege IAM**

The **Composer environment bucket is persistent** (stores `dags/`, `logs/`, `plugins/`, `data/`)

---

## Repo layout (best-practice)

- `dags/` contains only DAG definition files (entrypoints)
- `biodiv_airflow/` is a regular Python package containing shared code:
  - `config.py`: loads Airflow Variables and computes derived paths
  - `helpers.py`: generic helpers (GCS marker writing, config validation)
  - `dataflow_specs.py`: builds Dataflow Flex Template `body` payloads for each pipeline
- `terrafrom/` is a Terraform module that creates a Composer environment. It includes the following files separating code chunks in different Terraform modules:
  - `main.tf`: Infrastructure definition.
  - `provider.tf`: Provider config.
  - `iam.tf`: IAM policies
  - `variables.tf`: Input schema.
  - `versions.tf`: Backend and version pinning
  - `ouputs.tf`: outputs.
  - `.terraform.lock.hcl`: Terraform lockfile (pins provider versions/checksums).

Recommended structure:

```bash
.
├── biodiv_airflow/
│ ├── init.py
│ ├── config.py
│ ├── helpers.py
│ └── dataflow_specs.py
├── dags/
│  ├── biodiv_pipelines_dag.py
│  └── biodiv_ingestion.py # legacy
── terraform
│  ├── bootstrap
│  ├── cloudbuild.apply.yaml
│  ├── cloudbuild.destroy.yaml
│  ├── ephemeral
│  └── prod.tfvars
└── workflows
    └── biodiv_ephemeral_lifecycle.yaml



```

## Prerequisites for local dev

### 1. Set up Airflow for local dev

Use a dedicated venv for Airflow.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
```
Install Airflow

```bash
# Example; pin versions consistently in your local dev setup.
pip install "apache-airflow==2.10.*"
pip install "apache-airflow-providers-google"
```
### 2. Installed the packate locally

Install the repo package so the DAG can import biodiv_airflow.* reliably:

```bash
pip install -e .
python -c "import biodiv_airflow; print('OK:', biodiv_airflow.__file__)"
```

### 3. Local Airflow home

```bash
export AIRFLOW_HOME="$(pwd)/.airflow"
mkdir -p "$AIRFLOW_HOME"
```
Symlink your repo DAGs folder into $AIRFLOW_HOME/dags:

```bash
rm -rf "$AIRFLOW_HOME/dags"
ln -s "$(pwd)/dags" "$AIRFLOW_HOME/dags"
```

Check your Airflow settings:

```bash
airflow info | head
```
Check there are no import errors:

```bash
airflow dags list-import-errors
```
Confirm your DAG and tasks are present:

```bash
airflow dags list | grep biodiv_ingestion

airflow tasks list biodiv_ingestion
```

### 4. GCP access
- You must have credentials available via **Application Default Credentials (ADC)**:
```bash
  gcloud auth application-default login
```
The credentials must be able to:
* launch Dataflow jobs 
* read/write to the GCS bucket 
* read the Flex Template JSON files

### 5. Required Airflow connection
The DAG uses the default GCP connection:
* Connection ID:`google_cloud_default`
* Auth method: ADC (recommended)

Check it exists:

```bash
airflow connections get google_cloud_default
```

## Required Airflow Variables
These must be set in Composer (or locally via CLI) before running the DAG.

Check your variables:

```bash
airflow variables list 
```
Set your variables if not present already:

```bash
airflow variables set biodiv_gcp_project "<gcp-project-id>"
airflow variables set biodiv_bucket "<gcs-bucket>"
airflow variables set biodiv_flex_base "gs://<bucket>/biodiv-pipelines-dev/flex-templates"
airflow variables set biodiv_output_base "gs://<bucket>/biodiv-pipelines-dev"
airflow variables set biodiv_df_temp_location "gs://<bucket>/biodiv-pipelines-dev/temp"
airflow variables set biodiv_df_staging_location "gs://<bucket>/biodiv-pipelines-dev/staging"
airflow variables set biodiv_sdk_container_image "<region>-docker.pkg.dev/<project>/biodiversity-images/biodiversity-flex:<tag>"

airflow variables set elasticsearch_host "<elasticsearch-url>"
airflow variables set elasticsearch_user "<elasticsearch-user>"
airflow variables set elasticsearch_password "<elasticsearch-password>"

airflow variables set biodiv_bq_dataset "<bigquery-dataset>"
```

## What the DAG does

For a given logical date (ds), the DAG writes all run artifacts under a specific prefix:

```bash
gs://<bucket>/biodiv-pipelines-dev/runs/
  window_start=<ds>/
  run_ts=<ts_nodash>/
```
Pipeline outputs follow subfolders (taxonomy, occurrences, etc). Each stage also writes a lightweight _SUCCESS marker to simplify debugging and downstream orchestration.
For example: `gs://<bucket>/biodiv-pipelines-dev/runs/window_start=<ds>/taxonomy/_SUCCESS`

## Running DAG locally

1. Start Airflow: 
```bash
airflow standalone
``` 
2. Verify DAG loads:
```bash
airflow dags list-import-errors
airflow dags list | grep biodiv_ingestion
airflow dags list-import-errors
```
3. Test individual tasks

4. Pick a logical date (YYYY-MM-DD). Example:

```bash
airflow tasks test biodiv_ingestion validate_config 2026-01-29
airflow tasks test biodiv_ingestion run_taxonomy 2026-01-29
airflow tasks test biodiv_ingestion mark_taxonomy_success 2026-01-29
airflow tasks test biodiv_ingestion run_occurrences 2026-01-29
airflow tasks test biodiv_ingestion mark_occurrences_success 2026-01-29
```

4. Run the full DAG (local triggering):

```bash
airflow dags test biodiv_ingestion 2026-01-29
```

5. Verify outputs:
```bash
gsutil ls "gs://<bucket>/biodiv-pipelines-dev/runs/window_start=2026-01-29/"
gsutil ls gs://<bucket>/biodiv-pipelines-dev/runs/window_start=2026-01-29/run_ts=20260129T000000/taxonomy/
gsutil ls gs://<bucket>/biodiv-pipelines-dev/runs/window_start=2026-01-29/run_ts=20260129T000000/occurrences/raw
```

## NOTES
* The DAG is currently manual trigger only (schedule=None).
* _SUCCESS markers are used as lightweight completion artifacts for debugging and future orchestration.

---
## Deployment with Terraform

### 1) Create a local tfvars file (do not commit)

Create `prod.tfvars` (or equivalent) locally:

```hcl
project_idc = <gcp-project-id>

# Pipeline data bucket (temp/staging/output)
gcs_bucket_name = <gcs-bucket>

# Persistent Composer env bucket (dags/logs/plugins/data)
composer_env_bucket_name = <your-bucket-composer-storage>

# BigQuery datasets Dataflow writes to
bq_datasets = [
  <your-bq-dataset>
]

# Artifact Registry repos that store your Flex images
artifact_registry_repo_names = [
  <your-ar-repo>
]
```

### 2) Init / plan / apply

```bash
export TF_STATE_BUCKET="<your-bucket-tf-state>"

terraform init -backend-config="bucket=${TF_STATE_BUCKET}"
terraform plan  -var-file="prod.tfvars"
terraform apply -var-file="prod.tfvars"
```

### 3) Destroy (ephemeral environment)

```bash
terraform destroy -var-file="prod.tfvars"
```

**Note:** the Composer environment bucket is intended to be **persistent** and should not be managed/destroyed by this Terraform stack.
