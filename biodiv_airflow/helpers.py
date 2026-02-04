from airflow.providers.google.cloud.hooks.gcs import GCSHook
from biodiv_airflow.config import BiodivConfig


def split_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    # gcs_uri like "gs://bucket/path/to/object_or_prefix"
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Not a GCS URI: {gcs_uri}")
    no_scheme = gcs_uri[5:]
    bucket, _, path = no_scheme.partition("/")
    return bucket, path


def write_gcs_marker(gcs_marker_uri: str, gcp_conn_id: str = "google_cloud_default", **_):
    bucket, object_name = split_gcs_uri(gcs_marker_uri)

    hook = GCSHook(gcp_conn_id=gcp_conn_id)
    # Upload an empty marker file. This is idempotent: re-uploading overwrites.
    hook.upload(
        bucket_name=bucket,
        object_name=object_name,
        data=b"",
        mime_type="text/plain",
    )


def validate_config(cfg: BiodivConfig) -> str:
    required_vars = {
        "biodiv_gcp_project": cfg.gcp_project,
        "biodiv_bucket": cfg.gcs_bucket,
        "biodiv_sdk_container_image": cfg.sdk_container_image,
        "biodiv_output_base": cfg.output_base,
    }

    missing = []
    for k, v in required_vars.items():
        sv = str(v).strip()
        if not sv or "local" in sv:
            missing.append(k)

    if missing:
        raise ValueError(f"Missing or default Airflow Variables: {', '.join(missing)}")

    # Sanity checks for Flex template paths
    if not cfg.flex_base.startswith("gs://"):
        raise ValueError("FLEX_BASE must be a GCS path")

    # Check elastic search password is set
    if not cfg.elastic_password:
        raise ValueError("elasticsearch_password is empty")

    # Ensure run_prefix is well-formed (same check as your DAG)
    if "window_start=" not in cfg.run_prefix or "run_ts=" not in cfg.run_prefix:
        raise ValueError("run_prefix does not contain expected partitions")

    return "config_ok"
