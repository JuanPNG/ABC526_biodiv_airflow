from airflow.providers.google.cloud.hooks.gcs import GCSHook
from biodiv_airflow.config import BiodivConfig
from google.auth.transport.requests import Request
from google.oauth2 import id_token

import requests
import time


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


def call_delete_service(
    delete_url: str,
    *,
    timeout_s: int = 30,
    max_attempts: int = 5,
    base_sleep_s: float = 2.0,
) -> str:
    """
    Call a private Cloud Run delete-service using an OIDC ID token.
    Idempotent handling:
      - 2xx: success
      - 404: treat as already deleted (success)
      - 409: treat as already deleting / conflict (success)
    Retries on transient errors (5xx, 429, network).
    Fails loudly on 401/403.
    """

    _IDEMPOTENT_HTTP_STATUSES = {200, 202, 204, 404, 409}

    auth_req = Request()

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            token = id_token.fetch_id_token(auth_req, delete_url)

            resp = requests.post(
                delete_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout_s,
            )

            # Fast-fail on authn/authz problems — retries won't fix IAM.
            if resp.status_code in (401, 403):
                raise PermissionError(
                    f"Delete service auth failed ({resp.status_code}). "
                    f"Caller likely missing roles/run.invoker. Body: {resp.text[:500]}"
                )

            # Idempotent success statuses
            if resp.status_code in _IDEMPOTENT_HTTP_STATUSES:
                return f"delete_service_ok status={resp.status_code} body={resp.text[:1000]}"

            # Retryable statuses
            if resp.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(
                    f"Transient delete-service error status={resp.status_code} body={resp.text[:500]}"
                )

            # Non-retryable unexpected statuses
            resp.raise_for_status()
            return f"delete_service_ok status={resp.status_code} body={resp.text[:1000]}"

        except (requests.Timeout, requests.ConnectionError, RuntimeError) as e:
            last_err = e
            if attempt == max_attempts:
                break

            sleep_s = base_sleep_s * (2 ** (attempt - 1))
            time.sleep(sleep_s)

    raise RuntimeError(f"Delete service failed after {max_attempts} attempts: {last_err}")


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
