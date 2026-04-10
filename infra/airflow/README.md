# Airflow / batch service

## Что уже реализовано

В проекте есть 2 DAG'а:

1. `moderation_daily_report`
2. `moderation_validation_evaluate`

Оба DAG'а:

1. используют `DockerOperator` для основного batch run;
2. получают runtime secrets через Airflow Connections / Variables;
3. поддерживают rerun / overwrite;
4. пишут output'ы в S3 / MinIO.

## Task structure

## `moderation_daily_report`

1. `resolve_run_window`
2. `resolve_daily_report_runtime`
3. `generate_daily_report`
4. `publish_daily_report_metadata`

Schedule:
- `0 3 * * *` (ежедневно в 03:00 UTC)

## `moderation_validation_evaluate`

1. `resolve_dataset_source`
2. `resolve_validation_runtime`
3. `run_validation_evaluation`
4. `publish_validation_report_metadata`

Schedule:
- `None` (manual only)

Логи:
- основной batch-task `run_validation_evaluation` пишет читаемый summary-блок с ключевыми quality-метриками, confusion matrix и per-category breakdown;
- полный отчёт остаётся в `reports/validation/{dataset_version}/{dataset_kind}/{YYYY-MM-DD}.json`.

## Параметры DAG run

## `moderation_daily_report`

1. `run_date`
2. `lookback_days`
3. `overwrite`

## `moderation_validation_evaluate`

1. `dataset_version`
2. `dataset_kind`
3. `max_examples`
4. `include_redacted`
5. `shuffle`
6. `sample_seed`
7. `overwrite`

## Airflow Variables

Минимально нужны:

1. `MODERATION_IMAGE`
2. `DAILY_REPORTS_PREFIX` (optional, default `reports/daily`)
3. `VALIDATION_DATASETS_PREFIX` (optional, default `datasets/validation`)
4. `VALIDATION_REPORTS_PREFIX` (optional, default `reports/validation`)
5. `AIRFLOW_DOCKER_NETWORK_MODE` (optional, default `bridge`)
6. `PUSHGATEWAY_URL` (optional)
7. `OPENAI_API_KEY`
8. `OPENAI_MODEL` (optional)
9. `OPENAI_BASE_URL` (optional)
10. `OPENAI_TIMEOUT_S` (optional)
11. `POLICY_VERSION` (optional)
12. `PROMPT_VERSION` (optional)

## Airflow Connections

Нужно завести:

## `moderation_postgres`

Используется для чтения production moderation data.

## `moderation_s3`

Используется для:

1. чтения validation dataset;
2. записи daily / validation reports.

Ожидаемый формат:

1. `login` = access key
2. `password` = secret key
3. `extra.endpoint_url`
4. `extra.bucket`

Пример `extra`:

```json
{
  "endpoint_url": "http://minio:9000",
  "bucket": "carcase-mlprod"
}
```

## Что показывать на защите

1. DAG code
2. Graph view
3. Task logs
4. Airflow UI connections
5. Params при manual run
6. rerun / overwrite
7. output objects в S3 / MinIO

## Логи

Логи task'ов доступны:

1. в Airflow UI;
2. в volume с Airflow logs на сервере.

## Локальный / серверный bootstrap

Шаблон compose для Airflow и MinIO подготовлен в:

- `infra/airflow/docker-compose.yml`
- `infra/airflow/.env.example`

## Compose notes

1. `minio/minio` используется с тегом `latest`, чтобы не зависеть от несуществующего release tag.
2. Airflow стартует через `python -m airflow ...`, чтобы bootstrap не зависел от shell `PATH`.
3. В compose прокидывается `_PIP_ADDITIONAL_REQUIREMENTS=apache-airflow-providers-docker`, потому что DAG'и используют `DockerOperator`.
