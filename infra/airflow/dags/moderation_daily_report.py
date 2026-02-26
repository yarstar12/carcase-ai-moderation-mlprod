from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

DEFAULT_ARGS = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="moderation_daily_report",
    description="Daily moderation report from Postgres to S3 (idempotent, supports backfill).",
    start_date=datetime(2026, 2, 1),
    schedule="@daily",
    catchup=True,
    default_args=DEFAULT_ARGS,
    tags=["moderation", "batch", "s3", "postgres"],
):
    DockerOperator(
        task_id="generate_daily_report",
        image="{{ var.value.MODERATION_IMAGE }}",
        command="python -m carcase_ai_moderation.batch.daily_report --run-date {{ ds }}",
        environment={
            "DATABASE_URL": "{{ var.value.DATABASE_URL }}",
            "S3_ENDPOINT_URL": "{{ var.value.S3_ENDPOINT_URL }}",
            "S3_ACCESS_KEY": "{{ var.value.S3_ACCESS_KEY }}",
            "S3_SECRET_KEY": "{{ var.value.S3_SECRET_KEY }}",
            "S3_BUCKET": "{{ var.value.S3_BUCKET }}",
            "PUSHGATEWAY_URL": "{{ var.value.PUSHGATEWAY_URL | default('') }}",
        },
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
    )
