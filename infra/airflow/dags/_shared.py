from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from airflow.hooks.base import BaseHook
from airflow.models import Variable

LOGGER = logging.getLogger(__name__)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def get_required_variable(name: str) -> str:
    value = str(Variable.get(name)).strip()
    if not value:
        raise ValueError(f"Airflow Variable {name!r} must not be empty")
    return value


def get_variable(name: str, default: str) -> str:
    return str(Variable.get(name, default_var=default)).strip()


def build_daily_report_key(*, reports_prefix: str, run_date: str) -> str:
    prefix = reports_prefix.strip().strip("/")
    if not prefix:
        raise ValueError("reports_prefix must not be empty")
    return f"{prefix}/{run_date}.json"


def build_validation_report_key(
    *, reports_prefix: str, dataset_version: str, dataset_kind: str, run_date: str
) -> str:
    prefix = reports_prefix.strip().strip("/")
    if not prefix:
        raise ValueError("reports_prefix must not be empty")
    return f"{prefix}/{dataset_version}/{dataset_kind}/{run_date}.json"


def build_validation_dataset_key(
    *, datasets_prefix: str, dataset_version: str, dataset_kind: str
) -> str:
    prefix = datasets_prefix.strip().strip("/")
    if not prefix:
        raise ValueError("datasets_prefix must not be empty")
    suffix = "smoke.jsonl" if dataset_kind == "smoke" else "jsonl"
    return f"{prefix}/{dataset_version}.{suffix}"


def resolve_postgres_runtime(conn_id: str = "moderation_postgres") -> dict[str, str]:
    conn = BaseHook.get_connection(conn_id)
    extra = conn.extra_dejson or {}
    split = urlsplit(conn.get_uri().replace("postgres://", "postgresql://", 1))
    query: dict[str, str] = {}
    existing_query = dict(parse_qsl(split.query, keep_blank_values=True))
    query.update({key: value for key, value in existing_query.items() if value})
    for key in ("sslmode", "application_name"):
        value = extra.get(key)
        if value:
            query[key] = str(value)

    uri = urlunsplit(
        (split.scheme, split.netloc, split.path, urlencode(query) if query else "", "")
    )
    return {"DATABASE_URL": uri}


def resolve_s3_runtime(conn_id: str = "moderation_s3") -> dict[str, str]:
    conn = BaseHook.get_connection(conn_id)
    extra = conn.extra_dejson or {}

    endpoint_url = str(extra.get("endpoint_url") or "").strip()
    if not endpoint_url:
        scheme = str(conn.schema or extra.get("scheme") or "http").strip()
        host = str(conn.host or "").strip()
        port = f":{conn.port}" if conn.port else ""
        endpoint_url = f"{scheme}://{host}{port}" if host else ""

    bucket = str(extra.get("bucket") or "").strip()
    if not bucket:
        raise ValueError(
            "Airflow Connection 'moderation_s3' must define extra.bucket for the S3/MinIO bucket"
        )

    runtime = {
        "S3_ENDPOINT_URL": endpoint_url,
        "S3_ACCESS_KEY": str(conn.login or ""),
        "S3_SECRET_KEY": str(conn.password or ""),
        "S3_BUCKET": bucket,
    }
    if not runtime["S3_ACCESS_KEY"] or not runtime["S3_SECRET_KEY"]:
        raise ValueError(
            "Airflow Connection 'moderation_s3' must define login/password as access and secret keys"
        )
    return runtime


def resolve_common_runtime() -> dict[str, str]:
    runtime = {
        "image": get_required_variable("MODERATION_IMAGE"),
        "docker_network_mode": get_variable("AIRFLOW_DOCKER_NETWORK_MODE", "bridge"),
        "pushgateway_url": get_variable("PUSHGATEWAY_URL", ""),
    }
    LOGGER.info("Resolved Airflow runtime: image=%s", runtime["image"])
    return runtime
