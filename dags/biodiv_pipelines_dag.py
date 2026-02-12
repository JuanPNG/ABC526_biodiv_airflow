from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.google.cloud.operators.dataflow import DataflowStartFlexTemplateOperator
from airflow.providers.standard.operators.python import PythonOperator

from biodiv_airflow.config import load_config
from biodiv_airflow.helpers import write_gcs_marker, validate_config
from biodiv_airflow import dataflow_specs


default_args = {
    "owner": "biodiversity",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

cfg = load_config()

with DAG(
    dag_id="biodiv_pipelines_dag",
    description="Biodiv: taxonomy -> occurrences via Dataflow Flex Templates",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["biodiv", "dataflow", "flex"],
) as dag:

    validate = PythonOperator(
        task_id="validate_config",
        python_callable=lambda: validate_config(cfg),
    )

    run_taxonomy = DataflowStartFlexTemplateOperator(
        task_id="run_taxonomy",
        project_id=cfg.gcp_project,
        location=cfg.gcp_region,
        body=dataflow_specs.taxonomy_body(cfg),
        wait_until_finished=True,
    )

    mark_taxonomy_success = PythonOperator(
        task_id="mark_taxonomy_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.run_prefix}/taxonomy/_SUCCESS"},
    )

    run_occurrences = DataflowStartFlexTemplateOperator(
        task_id="run_occurrences",
        project_id=cfg.gcp_project,
        location=cfg.gcp_region,
        body=dataflow_specs.occurrences_body(cfg),
        wait_until_finished=True,
    )

    mark_occurrences_success = PythonOperator(
        task_id="mark_occurrences_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.raw_occurrences}/_SUCCESS"},
    )

    run_cleaning_occs = DataflowStartFlexTemplateOperator(
        task_id="run_cleaning_occs",
        project_id=cfg.gcp_project,
        location=cfg.gcp_region,
        body=dataflow_specs.cleaning_occs_body(cfg),
        wait_until_finished=True,
    )

    mark_cleaning_occs_success = PythonOperator(
        task_id="mark_cleaning_occs_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.cleaned_occurrences}/_SUCCESS"},
    )

    run_spatial_annotation = DataflowStartFlexTemplateOperator(
        task_id="run_spatial_annotation",
        project_id=cfg.gcp_project,
        location=cfg.gcp_region,
        body=dataflow_specs.spatial_annotation_body(cfg),
        wait_until_finished=True,
    )

    mark_spatial_annotation_success = PythonOperator(
        task_id="mark_spatial_annotation_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.spatial_annotations}/_SUCCESS"},
    )

    run_range_estimation = DataflowStartFlexTemplateOperator(
        task_id="run_range_estimation",
        project_id=cfg.gcp_project,
        location=cfg.gcp_region,
        body=dataflow_specs.range_estimation_body(cfg),
        wait_until_finished=True,
    )

    mark_range_estimation_success = PythonOperator(
        task_id="mark_range_estimation_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.range_estimates}/_SUCCESS"},
    )

    run_data_provenance = DataflowStartFlexTemplateOperator(
        task_id="run_data_provenance",
        project_id=cfg.gcp_project,
        location=cfg.gcp_region,
        body=dataflow_specs.data_provenance_body(cfg),
        wait_until_finished=True,
    )

    mark_data_provenance_success = PythonOperator(
        task_id="mark_data_provenance_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.data_provenance}/_SUCCESS"},
    )

    mark_pipelines_completion_success = PythonOperator(
        task_id="mark_pipelines_completion_success",
        python_callable=write_gcs_marker,
        op_kwargs={"gcs_marker_uri": f"{cfg.run_prefix}/_SUCCESS"},
    )

    (
        validate
        >> run_taxonomy
        >> mark_taxonomy_success
        >> run_occurrences
        >> mark_occurrences_success
        >> run_cleaning_occs
        >> mark_cleaning_occs_success
        >> run_spatial_annotation
        >> mark_spatial_annotation_success
        >> run_range_estimation
        >> mark_range_estimation_success
        >> run_data_provenance
        >> mark_data_provenance_success
        >> mark_pipelines_completion_success
    )
