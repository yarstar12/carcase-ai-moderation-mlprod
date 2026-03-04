from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

DEFAULT_ARGS = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="moderation_validation_evaluate",
    description=(
        "Evaluate moderation quality on validation dataset (smoke) "
        "and push metrics to Prometheus."
    ),
    start_date=datetime(2026, 2, 1),
    schedule="@daily",
    catchup=True,
    default_args=DEFAULT_ARGS,
    tags=["moderation", "batch", "quality", "s3", "pushgateway"],
):
    DockerOperator(
        task_id="evaluate_validation_smoke",
        image="{{ var.value.MODERATION_IMAGE }}",
        command=(
            "python -m carcase_ai_moderation.batch.validation_evaluate "
            "--run-date {{ ds }} "
            "--dataset-version {{ var.value.VALIDATION_DATASET_VERSION | default('v1') }} "
            "--dataset-kind smoke "
            "--require-openai"
        ),
        environment={
            "S3_ENDPOINT_URL": "{{ var.value.S3_ENDPOINT_URL }}",
            "S3_ACCESS_KEY": "{{ var.value.S3_ACCESS_KEY }}",
            "S3_SECRET_KEY": "{{ var.value.S3_SECRET_KEY }}",
            "S3_BUCKET": "{{ var.value.S3_BUCKET }}",
            "PUSHGATEWAY_URL": "{{ var.value.PUSHGATEWAY_URL | default('') }}",
            "OPENAI_API_KEY": "{{ var.value.OPENAI_API_KEY }}",
            "OPENAI_MODEL": "{{ var.value.OPENAI_MODEL | default('gpt-4o-mini') }}",
            "OPENAI_BASE_URL": (
                "{{ var.value.OPENAI_BASE_URL | default('https://api.openai.com/v1') }}"
            ),
            "OPENAI_TIMEOUT_S": "{{ var.value.OPENAI_TIMEOUT_S | default('10.0') }}",
            "POLICY_VERSION": "{{ var.value.POLICY_VERSION | default('v1') }}",
            "PROMPT_VERSION": "{{ var.value.PROMPT_VERSION | default('v1') }}",
        },
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
    )
