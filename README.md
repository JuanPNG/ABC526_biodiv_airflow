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

---

## Repo layout (best-practice)

- `dags/` contains only DAG definition files (entrypoints)
- `biodiv_airflow/` is a regular Python package containing shared code:
  - `config.py`: loads Airflow Variables and computes derived paths
  - `helpers.py`: generic helpers (GCS marker writing, config validation)
  - `dataflow_specs.py`: builds Dataflow Flex Template `body` payloads for each pipeline

Recommended structure:

```bash
.
├── biodiv_airflow/
│ ├── init.py
│ ├── config.py
│ ├── helpers.py
│ └── dataflow_specs.py
└── dags/
├── biodiv_pipelines_dag.py
└── biodiv_ingestion.py # legacy

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