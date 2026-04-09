from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, get_current_context, task
from airflow.providers.docker.operators.docker import DockerOperator

from _shared import (
    build_daily_report_key,
    get_variable,
    parse_bool,
    resolve_common_runtime,
    resolve_postgres_runtime,
    resolve_s3_runtime,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="moderation_daily_report",
    description="Build a daily moderation report from Postgres and publish it to S3/MinIO.",
    start_date=datetime(2026, 2, 1),
    schedule="@daily",
    catchup=True,
    default_args=DEFAULT_ARGS,
    render_template_as_native_obj=True,
    params={
        "run_date": "",
        "lookback_days": 7,
        "overwrite": False,
    },
    tags=["moderation", "batch", "daily-report", "s3", "postgres"],
)
def moderation_daily_report() -> None:
    @task(task_id="resolve_run_window")
    def resolve_run_window() -> dict[str, object]:
        context = get_current_context()
        params = context["params"]
        run_date = str(params.get("run_date") or context["ds"]).strip()
        lookback_days = int(params.get("lookback_days") or 7)
        overwrite = parse_bool(params.get("overwrite"))
        reports_prefix = get_variable("DAILY_REPORTS_PREFIX", "reports/daily")
        report_key = build_daily_report_key(reports_prefix=reports_prefix, run_date=run_date)
        return {
            "run_date": run_date,
            "lookback_days": lookback_days,
            "overwrite": overwrite,
            "reports_prefix": reports_prefix,
            "report_key": report_key,
        }

    @task(task_id="resolve_daily_report_runtime")
    def resolve_daily_report_runtime(run_cfg: dict[str, object]) -> dict[str, object]:
        runtime = {}
        runtime.update(run_cfg)
        runtime.update(resolve_common_runtime())
        runtime.update(resolve_postgres_runtime())
        runtime.update(resolve_s3_runtime())
        LOGGER.info(
            "Daily report runtime resolved: run_date=%s key=%s overwrite=%s",
            runtime["run_date"],
            runtime["report_key"],
            runtime["overwrite"],
        )
        return runtime

    runtime = resolve_daily_report_runtime(resolve_run_window())

    build_report = DockerOperator(
        task_id="generate_daily_report",
        image="{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['image'] }}",
        command=(
            "python -m carcase_ai_moderation.batch.daily_report "
            "--run-date {{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['run_date'] }} "
            "--lookback-days {{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['lookback_days'] }} "
            "--s3-prefix {{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['reports_prefix'] }}"
            "{% if ti.xcom_pull(task_ids='resolve_daily_report_runtime')['overwrite'] %} --overwrite{% endif %}"
        ),
        environment={
            "DATABASE_URL": "{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['DATABASE_URL'] }}",
            "S3_ENDPOINT_URL": "{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['S3_ENDPOINT_URL'] }}",
            "S3_ACCESS_KEY": "{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['S3_ACCESS_KEY'] }}",
            "S3_SECRET_KEY": "{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['S3_SECRET_KEY'] }}",
            "S3_BUCKET": "{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['S3_BUCKET'] }}",
            "PUSHGATEWAY_URL": "{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['pushgateway_url'] }}",
        },
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        network_mode="{{ ti.xcom_pull(task_ids='resolve_daily_report_runtime')['docker_network_mode'] }}",
    )

    @task(task_id="publish_daily_report_metadata")
    def publish_daily_report_metadata(runtime_cfg: dict[str, object]) -> None:
        LOGGER.info(
            "Daily report finished: run_date=%s key=%s overwrite=%s bucket=%s",
            runtime_cfg["run_date"],
            runtime_cfg["report_key"],
            runtime_cfg["overwrite"],
            runtime_cfg["S3_BUCKET"],
        )

    build_report >> publish_daily_report_metadata(runtime)


moderation_daily_report()
