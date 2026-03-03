# Airflow (batch service) — notes

Цель: ежедневный batch‑отчёт по модерации из Postgres → S3/MinIO.

## DAG

Файл DAG: `infra/airflow/dags/moderation_daily_report.py`

Оператор: `DockerOperator`, запускает команду:

```bash
python -m carcase_ai_moderation.batch.daily_report --run-date {{ ds }}
```

Идемпотентность обеспечивается на уровне джобы: если объект отчёта уже есть в S3, задача завершится успешно без перезаписи.

## Требования к Airflow окружению

- Airflow 2.x
- установлен провайдер Docker: `apache-airflow-providers-docker`
- доступ к Docker Engine (обычно `/var/run/docker.sock`) на воркере, где выполняется задача

## Переменные (Airflow Variables)

DAG ожидает значения в `Airflow Variables`:
- `MODERATION_IMAGE` — docker image с проектом (например `ghcr.io/<org>/<repo>:<tag>`)
- `DATABASE_URL` — строка подключения к удалённому Postgres
- `S3_ENDPOINT_URL` — endpoint MinIO/S3
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` — креды/бакет
- (опционально) `PUSHGATEWAY_URL` — если задан, batch пушит метрики отчёта в Pushgateway

## Backfill (пример)

```bash
airflow dags backfill moderation_daily_report -s 2026-02-01 -e 2026-02-07
```

## Planned: validation evaluation DAG

Отдельным DAG планируется регулярная оценка качества на validation dataset (golden set):
- прогон smoke‑набора — часто (регрессионный контроль),
- прогон full‑набора — периодически или вручную (полная переоценка).

Описание подхода: `docs/QUALITY_EVALUATION.md`.
