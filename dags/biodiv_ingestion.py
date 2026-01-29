from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.providers.google.cloud.operators.dataflow import (
    DataflowStartFlexTemplateOperator,
)

from airflow.providers.standard.operators.python import PythonOperator


# --------- Config (Variables in Composer) ----------
GCP_PROJECT = Variable.get("biodiv_gcp_project", default_var="local-project")
GCP_REGION = Variable.get("biodiv_gcp_region", default_var="europe-west2")
GCS_BUCKET = Variable.get("biodiv_bucket", default_var="local-bucket")

IMAGE_TAG = Variable.get("biodiv_image_tag", default_var="flex-image-260129-101318")

FLEX_BASE = Variable.get(
    "biodiv_flex_base",
    default_var=f"gs://{GCS_BUCKET}/biodiv-pipelines-dev/flex-templates",
)

OUTPUT_BASE = Variable.get(
    "biodiv_output_base",
    default_var=f"gs://{GCS_BUCKET}/biodiv-pipelines-dev",
)

DF_TEMP_LOCATION = Variable.get(
    "biodiv_df_temp_location",
    default_var=f"gs://{GCS_BUCKET}/biodiv-pipelines-dev/temp",
)

DF_STAGING_LOCATION = Variable.get(
    "biodiv_df_staging_location",
    default_var=f"gs://{GCS_BUCKET}/biodiv-pipelines-dev/staging",
)

SDK_CONTAINER_IMAGE = Variable.get(
    "biodiv_sdk_container_image",
    default_var=f"{GCP_REGION}-docker.pkg.dev/{GCP_PROJECT}/biodiversity-images/biodiversity-flex:{IMAGE_TAG}",
)

ELASTIC_HOST = Variable.get(
    "elasticsearch_host",
    default_var="local-host",
)

ELASTIC_USER = Variable.get("elasticsearch_user", default_var="elastic")

ELASTIC_PASSWORD = Variable.get("elasticsearch_password", default_var="")

BQ_DATASET = Variable.get("biodiv_bq_dataset", default_var="TESTJPNG")


default_args = {
    "owner": "biodiv",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="biodiv_ingestion",
    description="Biodiv: taxonomy -> occurrences via Dataflow Flex Templates",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags={"biodiv", "dataflow", "flex"},
) as dag:

    ###############
    ### Helpers ###
    ###############
    def _split_gcs_uri(gcs_uri: str) -> tuple[str, str]:
        # gcs_uri like "gs://bucket/path/to/object_or_prefix"
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Not a GCS URI: {gcs_uri}")
        no_scheme = gcs_uri[5:]
        bucket, _, path = no_scheme.partition("/")
        return bucket, path


    def write_gcs_marker(gcs_marker_uri: str, gcp_conn_id: str = "google_cloud_default", **_):
        bucket, object_name = _split_gcs_uri(gcs_marker_uri)

        hook = GCSHook(gcp_conn_id=gcp_conn_id)
        # Upload an empty marker file. This is idempotent: re-uploading overwrites.
        hook.upload(
            bucket_name=bucket,
            object_name=object_name,
            data=b"",
            mime_type="text/plain",
        )

    def validate_config():
        required_vars = {
            "biodiv_gcp_project": GCP_PROJECT,
            "biodiv_bucket": GCS_BUCKET,
            "biodiv_sdk_container_image": SDK_CONTAINER_IMAGE,
            "biodiv_output_base": OUTPUT_BASE,
        }

        missing = []
        for k, v in required_vars.items():
            sv = str(v).strip()
            if not sv or "local" in sv:
                missing.append(k)

        if missing:
            raise ValueError(
                f"Missing or default Airflow Variables: {', '.join(missing)}"
            )

        # Sanity checks for Flex template paths
        if not FLEX_BASE.startswith("gs://"):
            raise ValueError("FLEX_BASE must be a GCS path")

        # Check elastic search password is set
        if not ELASTIC_PASSWORD:
            raise ValueError("elasticsearch_password is empty")

        # Ensure run_prefix is well-formed
        if "window_start=" not in run_prefix or "run_ts=" not in run_prefix:
            raise ValueError("run_prefix does not contain expected partitions")

        return "config_ok"


    ###############
    # Helpers end #
    ###############

    # Keep artifacts isolated per DAG run.
    # Eases incremental/“look-back” orchestration
    run_prefix = (
        f"{OUTPUT_BASE}/runs/"
        f"window_start={{{{ ds }}}}/"
        f"run_ts={{{{ ts_nodash }}}}"
    )

    # Pipeline templates path
    taxonomy_template = f"{FLEX_BASE}/flex_taxonomy.json"
    occurrences_template = f"{FLEX_BASE}/flex_occurrences.json"

    # Pipeline artifacts path
    taxonomy_validated = f"{run_prefix}/taxonomy/taxonomy_validated.jsonl"

    # 1. Discover new species
    # TODO: Implement species discovery task

    # 2. Validate config arguments before running pipelines
    validate = PythonOperator(
        task_id="validate_config",
        python_callable=validate_config,
    )

    # 3. Run taxonomy pipeline
    run_taxonomy = DataflowStartFlexTemplateOperator(
        task_id="run_taxonomy",
        project_id=GCP_PROJECT,
        location=GCP_REGION,
        body={
            "launchParameter": {
                "jobName": "biodiv-taxonomy-{{ ds_nodash }}-{{ ts_nodash | lower }}",
                "containerSpecGcsPath": taxonomy_template,
                "parameters": {
                    "pipeline": "taxonomy",
                    # Pipeline parameters
                    "host": ELASTIC_HOST,
                    "user": ELASTIC_USER ,
                    "password": ELASTIC_PASSWORD,
                    "index": "data_portal",
                    "size": "10",
                    "pages": "1",
                    # GCS Output path
                    "output": f"{run_prefix}/taxonomy/taxonomy",
                    # BigQuery Output
                    "bq_schema": f"gs://{GCS_BUCKET}/biodiv-pipelines-dev/schemas/bq_taxonomy_schema.json",
                    "bq_table": f"{GCP_PROJECT}:{BQ_DATASET}.bq_taxonomy_validated",

                    # Required for custom container / Beam worker imports
                    "sdk_container_image": SDK_CONTAINER_IMAGE,
                    "experiments": "use_runner_v2",
                },
                "environment": {
                    "tempLocation": DF_TEMP_LOCATION,
                    "stagingLocation": DF_STAGING_LOCATION,
                    # For observability later in Dataflow/Debugging
                    "additionalUserLabels": {
                        "app": "biodiv",
                        "dag": "biodiv_ingestion",
                        "pipeline": "taxonomy",
                        "window_start": "{{ ds_nodash }}",
                    },
                },
            }
        },
        wait_until_finished=True,
    )

    mark_taxonomy_success = PythonOperator(
        task_id="mark_taxonomy_success",
        python_callable=write_gcs_marker,
        op_kwargs={
            "gcs_marker_uri": f"{run_prefix}/taxonomy/_SUCCESS",
        },
    )

    # 4. Run occurrences pipeline
    run_occurrences = DataflowStartFlexTemplateOperator(
        task_id="run_occurrences",
        project_id=GCP_PROJECT,
        location=GCP_REGION,
        body={
            "launchParameter": {
                "jobName": "biodiv-occurrences-{{ ds_nodash }}-{{ ts_nodash | lower }}",
                "containerSpecGcsPath": occurrences_template,
                "parameters": {
                    "pipeline": "occurrences",
                    # Pipeline parameters
                    "validated_input": taxonomy_validated,
                    "output_dir": f"{run_prefix}/occurrences/raw",
                    "limit": "100",
                    # Required for custom container / Beam worker imports
                    "sdk_container_image": SDK_CONTAINER_IMAGE,
                    "experiments": "use_runner_v2",
                },
                "environment": {
                    "tempLocation": DF_TEMP_LOCATION,
                    "stagingLocation": DF_STAGING_LOCATION,
                    # For observability later in Dataflow/Debugging
                    "additionalUserLabels": {
                        "app": "biodiv",
                        "dag": "biodiv_ingestion",
                        "pipeline": "occurrences",
                        "window_start": "{{ ds_nodash }}",
                    },

                },
            }
        },
        wait_until_finished=True,
    )

    mark_occurrences_success = PythonOperator(
        task_id="mark_occurrences_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{run_prefix}/occurrences/_SUCCESS"},
    )

    # Instantiate DAG tasks & dependencies
    validate >> run_taxonomy >> mark_taxonomy_success >> run_occurrences >> mark_occurrences_success


