# Airflow (батч‑сервис) — заметки

Цель: ежедневный пакетный отчёт по модерации из Postgres → S3/MinIO.

## DAG

Файл DAG: `infra/airflow/dags/moderation_daily_report.py`

Оператор: `DockerOperator`, запускает команду:

```bash
python -m carcase_ai_moderation.batch.daily_report --run-date {{ ds }}
```

Идемпотентность обеспечивается на уровне джобы: если объект отчёта уже есть в S3, задача завершится успешно без перезаписи.

## Требования к Airflow окружению

- Airflow версии 2.x
- установлен провайдер Docker: `apache-airflow-providers-docker`
- доступ к демону Docker (обычно `/var/run/docker.sock`) на воркере, где выполняется задача

## Переменные Airflow

DAG ожидает значения в переменных Airflow (`Airflow Variables`):
- `MODERATION_IMAGE` — Docker‑образ с проектом (например `ghcr.io/<org>/<repo>:<tag>`)
- `DATABASE_URL` — строка подключения к удалённому Postgres
- `S3_ENDPOINT_URL` — адрес MinIO/S3
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` — креды/бакет
- (опционально) `PUSHGATEWAY_URL` — если задан, пакетная джоба отправляет метрики отчёта в Pushgateway

## Прогон за прошлые даты (backfill)

```bash
airflow dags backfill moderation_daily_report -s 2026-02-01 -e 2026-02-07
```

## DAG для оценки качества на датасете

Файл DAG: `infra/airflow/dags/moderation_validation_evaluate.py`

Задача: регулярная оценка качества на валидационном датасете (эталонном наборе примеров):
- прогон короткого набора `smoke` — часто (регрессионный контроль),
- прогон полного набора `full` — периодически или вручную (можно вынести в отдельный `@weekly` DAG или запускать вручную).

Описание подхода: `docs/QUALITY_EVALUATION.md`.
