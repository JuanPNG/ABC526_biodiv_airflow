# Biodiv Ingestion DAG. How to Run

This DAG (`biodiv_ingestion`) orchestrates two Dataflow Flex Template pipelines in Google Cloud Composer:
1) **taxonomy**
2) **occurrences**
3) Others to be added soon.

It is designed to run in **Cloud Composer 3** (Airflow 2.10.x), but can be tested locally with `airflow standalone`.

---

## Prerequisites

### 1. Set up Airflow for local dev

Define the location of your Airflow home directory:
```bash
export AIRFLOW_HOME="$(pwd)/.airflow"
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

### 2. GCP access
- You must have credentials available via **Application Default Credentials (ADC)**:
```bash
  gcloud auth application-default login
```
The credentials must be able to:
* launch Dataflow jobs 
* read/write to the GCS bucket 
* read the Flex Template JSON files

### 2. Required Airflow connection
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

For a given logical date (ds):

1. validate_config
   * Ensures required Airflow Variables are present and sane.

2. run_taxonomy
   * Launches the taxonomy Dataflow Flex Template. 
   * Writes outputs under:
   
```bash
gs://<bucket>/biodiv-pipelines-dev/runs/
  window_start=<ds>/
  run_ts=<ts_nodash>/
  taxonomy/
```
3. mark_taxonomy_success
* Writes a completion marker: `gs://<bucket>/biodiv-pipelines-dev/runs/window_start=<ds>/taxonomy/_SUCCESS`

```bash
.../taxonomy/_SUCCESS 
```

4. run_occurrences
   * Launches the occurrences Dataflow Flex Template.
   * Reads taxnomy output: `gs://<bucket>/biodiv-pipelines-dev/runs/window_start=<ds>/taxonomy/taxonomy_validated.jsonl`
   * Writes outputs under: `gs://<bucket>/biodiv-pipelines-dev/runs/window_start=<ds>/occurrences/raw`

5. mark_occurrences_success
* Writes a completion marker: `gs://<bucket>/biodiv-pipelines-dev/runs/window_start=<ds>/occurrences/raw/_SUCCESS`

## Running DAG locally

1. Start Airflow: 
```bash
airflow standalone
``` 
2. Verify DAG loads:
```bash
airflow dags list | grep biodiv_ingestion
airflow dags list-import-errors
```
3. Test individual tasks
```bash
airflow tasks test biodiv_ingestion validate_config 2026-01-29
airflow tasks test biodiv_ingestion run_taxonomy 2026-01-29
airflow tasks test biodiv_ingestion mark_taxonomy_success 2026-01-29
airflow tasks test biodiv_ingestion run_occurrences 2026-01-29
airflow tasks test biodiv_ingestion mark_occurrences_success 2026-01-29
```

4. Run the full DAG:
```bash
airflow dags test biodiv_ingestion 2026-01-29
```
5. Verify outputs:
```bash
gsutil ls gs://<bucket>/biodiv-pipelines-dev/runs/window_start=2026-01-29/run_ts=20260129T000000/taxonomy/
gsutil ls gs://<bucket>/biodiv-pipelines-dev/runs/window_start=2026-01-29/run_ts=20260129T000000/occurrences/raw
```

## NOTES
* The DAG is currently manual trigger only (schedule=None).
* _SUCCESS markers are used as lightweight completion artifacts for debugging and future orchestration.