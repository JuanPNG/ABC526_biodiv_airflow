from dataclasses import dataclass
from airflow.models import Variable


@dataclass(frozen=True)
class BiodivConfig:
    # --------- Config (Variables in Composer) ----------
    gcp_project: str
    gcp_region: str
    gcs_bucket: str

    image_tag: str

    flex_base: str
    output_base: str
    df_temp_location: str
    df_staging_location: str
    sdk_container_image: str
    dataflow_service_account: str

    elastic_host: str
    elastic_user: str
    elastic_password: str

    bq_dataset: str

    # --------- Derived (computed) ----------
    run_prefix: str

    # Templates
    taxonomy_template: str
    occurrences_template: str
    occs_cleaning_template: str
    spatial_annotation_template: str
    range_estimates_template: str
    data_provenance_template: str

    # Artifacts
    taxonomy_validated: str
    raw_occurrences: str
    cleaned_occurrences: str
    spatial_annotations: str
    range_estimates: str
    data_provenance: str

    # Input data
    continental_land_shapefile: str
    centroids_shapefile: str
    climate_layers: str
    ecoregions_vector: str


def load_config() -> BiodivConfig:
    """
    Parse-time config load. Uses Variable.get with default_var.
    """
    gcp_project = Variable.get("biodiv_gcp_project", default_var=None)
    gcp_region = Variable.get("biodiv_gcp_region", default_var=None)
    gcs_bucket = Variable.get("biodiv_bucket", default_var=None)

    image_tag = Variable.get("biodiv_image_tag", default_var=None)

    flex_base = Variable.get(
        "biodiv_flex_base",
        default_var=f"gs://{gcs_bucket}/biodiv-pipelines-dev/flex-templates",
    )
    output_base = Variable.get(
        "biodiv_output_base",
        default_var=f"gs://{gcs_bucket}/biodiv-pipelines-dev",
    )
    df_temp_location = Variable.get(
        "biodiv_df_temp_location",
        default_var=f"gs://{gcs_bucket}/biodiv-pipelines-dev/temp",
    )
    df_staging_location = Variable.get(
        "biodiv_df_staging_location",
        default_var=f"gs://{gcs_bucket}/biodiv-pipelines-dev/staging",
    )

    sdk_container_image = Variable.get(
        "biodiv_sdk_container_image",
        default_var=f"{gcp_region}-docker.pkg.dev/{gcp_project}/biodiversity-images/biodiversity-flex:{image_tag}",
    )

    dataflow_service_account = Variable.get(
        "biodiv_dataflow_worker_sa_email",
        default_var=None
    )

    elastic_host = Variable.get("elasticsearch_host", default_var=None)
    elastic_user = Variable.get("elasticsearch_user", default_var=None)
    elastic_password = Variable.get("elasticsearch_password", default_var=None)

    bq_dataset = Variable.get("biodiv_bq_dataset", default_var=None)

    # Keep artifacts isolated per DAG run
    run_prefix = (
        f"{output_base}/runs/"
        f"window_start={{{{ ds }}}}/"
        f"run_ts={{{{ ts_nodash }}}}"
    )

    # Templates
    taxonomy_template = f"{flex_base}/flex_taxonomy.json"
    occurrences_template = f"{flex_base}/flex_occurrences.json"
    occs_cleaning_template = f"{flex_base}/flex_cleaning_occs.json"
    spatial_annotation_template = f"{flex_base}/flex_spatial_annotations.json"
    range_estimates_template = f"{flex_base}/flex_range_estimation.json"
    data_provenance_template = f"{flex_base}/flex_data_provenance.json"

    # Artifacts
    taxonomy_validated = f"{run_prefix}/taxonomy/taxonomy_validated.jsonl"
    raw_occurrences = f"{run_prefix}/occurrences/raw"
    cleaned_occurrences = f"{run_prefix}/occurrences/cleaned"
    spatial_annotations = f"{run_prefix}/spatial"
    range_estimates = f"{run_prefix}/range_estimates"
    data_provenance = f"{run_prefix}/data_provenance"

    # Input data
    continental_land_shapefile = f"{output_base}/data/spatial_processing/ne_10m_land/ne_10m_land.shp"
    centroids_shapefile = f"{output_base}/data/spatial_processing/ne_10m_admin_0_label_points/ne_10m_admin_0_label_points.shp"
    climate_layers = f"{output_base}/data/climate"
    ecoregions_vector = f"{output_base}/data/bioregions/Ecoregions2017.zip"

    return BiodivConfig(
        gcp_project=gcp_project,
        gcp_region=gcp_region,
        gcs_bucket=gcs_bucket,
        image_tag=image_tag,
        flex_base=flex_base,
        output_base=output_base,
        df_temp_location=df_temp_location,
        df_staging_location=df_staging_location,
        sdk_container_image=sdk_container_image,
        dataflow_service_account=dataflow_service_account,
        elastic_host=elastic_host,
        elastic_user=elastic_user,
        elastic_password=elastic_password,
        bq_dataset=bq_dataset,
        run_prefix=run_prefix,
        taxonomy_template=taxonomy_template,
        occurrences_template=occurrences_template,
        occs_cleaning_template=occs_cleaning_template,
        spatial_annotation_template=spatial_annotation_template,
        range_estimates_template=range_estimates_template,
        data_provenance_template=data_provenance_template,
        taxonomy_validated=taxonomy_validated,
        raw_occurrences=raw_occurrences,
        cleaned_occurrences=cleaned_occurrences,
        spatial_annotations=spatial_annotations,
        range_estimates=range_estimates,
        data_provenance=data_provenance,
        continental_land_shapefile=continental_land_shapefile,
        centroids_shapefile=centroids_shapefile,
        climate_layers=climate_layers,
        ecoregions_vector=ecoregions_vector,
    )
