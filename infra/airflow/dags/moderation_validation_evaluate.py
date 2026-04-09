from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.operators.python import get_current_context
from airflow.providers.docker.operators.docker import DockerOperator

from _shared import (
    build_validation_dataset_key,
    build_validation_report_key,
    get_variable,
    get_required_variable,
    parse_bool,
    resolve_common_runtime,
    resolve_s3_runtime,
)

LOGGER = logging.getLogger(__name__)
DOCKER_NETWORK_MODE = get_required_variable("AIRFLOW_DOCKER_NETWORK_MODE")

DEFAULT_ARGS = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="moderation_validation_evaluate",
    description="Evaluate moderation quality on a validation dataset and publish the report to S3/MinIO.",
    start_date=datetime(2026, 2, 1),
    schedule="@daily",
    catchup=False,
    default_args=DEFAULT_ARGS,
    render_template_as_native_obj=True,
    params={
        "dataset_version": "v1",
        "dataset_kind": "smoke",
        "max_examples": 0,
        "include_redacted": False,
        "shuffle": False,
        "sample_seed": 42,
        "overwrite": False,
    },
    tags=["moderation", "batch", "validation", "quality", "s3"],
)
def moderation_validation_evaluate() -> None:
    @task(task_id="resolve_dataset_source")
    def resolve_dataset_source() -> dict[str, object]:
        context = get_current_context()
        params = context["params"]
        run_date = context["ds"]
        dataset_version = str(params.get("dataset_version") or "v1").strip()
        dataset_kind = str(params.get("dataset_kind") or "smoke").strip()
        if dataset_kind not in {"smoke", "full"}:
            raise ValueError("dataset_kind must be smoke or full")

        max_examples_raw = int(params.get("max_examples") or 0)
        max_examples = max_examples_raw if max_examples_raw > 0 else None
        include_redacted = parse_bool(params.get("include_redacted"))
        shuffle = parse_bool(params.get("shuffle"))
        sample_seed_raw = params.get("sample_seed")
        sample_seed = int(sample_seed_raw) if sample_seed_raw not in (None, "") else None
        overwrite = parse_bool(params.get("overwrite"))
        datasets_prefix = get_variable("VALIDATION_DATASETS_PREFIX", "datasets/validation")
        reports_prefix = get_variable("VALIDATION_REPORTS_PREFIX", "reports/validation")
        dataset_key = build_validation_dataset_key(
            datasets_prefix=datasets_prefix,
            dataset_version=dataset_version,
            dataset_kind=dataset_kind,
        )
        report_key = build_validation_report_key(
            reports_prefix=reports_prefix,
            dataset_version=dataset_version,
            dataset_kind=dataset_kind,
            run_date=run_date,
        )
        return {
            "run_date": run_date,
            "dataset_version": dataset_version,
            "dataset_kind": dataset_kind,
            "max_examples": max_examples,
            "include_redacted": include_redacted,
            "shuffle": shuffle,
            "sample_seed": sample_seed,
            "overwrite": overwrite,
            "datasets_prefix": datasets_prefix,
            "reports_prefix": reports_prefix,
            "dataset_key": dataset_key,
            "report_key": report_key,
        }

    @task(task_id="resolve_validation_runtime")
    def resolve_validation_runtime(dataset_cfg: dict[str, object]) -> dict[str, object]:
        runtime = {}
        runtime.update(dataset_cfg)
        runtime.update(resolve_common_runtime())
        runtime.update(resolve_s3_runtime())
        runtime.update(
            {
                "OPENAI_API_KEY": Variable.get("OPENAI_API_KEY"),
                "OPENAI_MODEL": Variable.get("OPENAI_MODEL", default_var="gpt-4o-mini"),
                "OPENAI_BASE_URL": Variable.get(
                    "OPENAI_BASE_URL", default_var="https://api.openai.com/v1"
                ),
                "OPENAI_TIMEOUT_S": Variable.get("OPENAI_TIMEOUT_S", default_var="10.0"),
                "POLICY_VERSION": Variable.get("POLICY_VERSION", default_var="v1"),
                "PROMPT_VERSION": Variable.get("PROMPT_VERSION", default_var="v1"),
            }
        )
        LOGGER.info(
            "Validation runtime resolved: dataset=%s/%s report_key=%s overwrite=%s",
            runtime["dataset_version"],
            runtime["dataset_kind"],
            runtime["report_key"],
            runtime["overwrite"],
        )
        return runtime

    runtime = resolve_validation_runtime(resolve_dataset_source())

    evaluate = DockerOperator(
        task_id="run_validation_evaluation",
        image="{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['image'] }}",
        command=(
            "python -m carcase_ai_moderation.batch.validation_evaluate "
            "--run-date {{ ti.xcom_pull(task_ids='resolve_validation_runtime')['run_date'] }} "
            "--dataset-version {{ ti.xcom_pull(task_ids='resolve_validation_runtime')['dataset_version'] }} "
            "--dataset-kind {{ ti.xcom_pull(task_ids='resolve_validation_runtime')['dataset_kind'] }} "
            "--datasets-prefix {{ ti.xcom_pull(task_ids='resolve_validation_runtime')['datasets_prefix'] }} "
            "--reports-prefix {{ ti.xcom_pull(task_ids='resolve_validation_runtime')['reports_prefix'] }} "
            "--require-openai"
            "{% set max_examples = ti.xcom_pull(task_ids='resolve_validation_runtime')['max_examples'] %}"
            "{% if max_examples %} --max-examples {{ max_examples }}{% endif %}"
            "{% if ti.xcom_pull(task_ids='resolve_validation_runtime')['include_redacted'] %} --include-redacted{% endif %}"
            "{% if ti.xcom_pull(task_ids='resolve_validation_runtime')['shuffle'] %} --shuffle{% endif %}"
            "{% set sample_seed = ti.xcom_pull(task_ids='resolve_validation_runtime')['sample_seed'] %}"
            "{% if sample_seed is not none %} --sample-seed {{ sample_seed }}{% endif %}"
            "{% if ti.xcom_pull(task_ids='resolve_validation_runtime')['overwrite'] %} --overwrite{% endif %}"
        ),
        environment={
            "S3_ENDPOINT_URL": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['S3_ENDPOINT_URL'] }}",
            "S3_ACCESS_KEY": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['S3_ACCESS_KEY'] }}",
            "S3_SECRET_KEY": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['S3_SECRET_KEY'] }}",
            "S3_BUCKET": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['S3_BUCKET'] }}",
            "PUSHGATEWAY_URL": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['pushgateway_url'] }}",
            "OPENAI_API_KEY": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['OPENAI_API_KEY'] }}",
            "OPENAI_MODEL": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['OPENAI_MODEL'] }}",
            "OPENAI_BASE_URL": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['OPENAI_BASE_URL'] }}",
            "OPENAI_TIMEOUT_S": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['OPENAI_TIMEOUT_S'] }}",
            "POLICY_VERSION": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['POLICY_VERSION'] }}",
            "PROMPT_VERSION": "{{ ti.xcom_pull(task_ids='resolve_validation_runtime')['PROMPT_VERSION'] }}",
        },
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        network_mode=DOCKER_NETWORK_MODE,
        mount_tmp_dir=False,
    )

    @task(task_id="publish_validation_report_metadata")
    def publish_validation_report_metadata(runtime_cfg: dict[str, object]) -> None:
        LOGGER.info(
            "Validation evaluation finished: dataset=%s/%s dataset_key=%s report_key=%s overwrite=%s bucket=%s",
            runtime_cfg["dataset_version"],
            runtime_cfg["dataset_kind"],
            runtime_cfg["dataset_key"],
            runtime_cfg["report_key"],
            runtime_cfg["overwrite"],
            runtime_cfg["S3_BUCKET"],
        )

    runtime >> evaluate >> publish_validation_report_metadata(runtime)


moderation_validation_evaluate()
