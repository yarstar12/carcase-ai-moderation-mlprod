# CARCASE — AI Moderation service

Репозиторий содержит сервис AI‑модерации пользовательского текста (UGC) для продукта **CARCASE ARENA** (Telegram Mini App).

Цель: модерировать `squad name / squad description` при создании/редактировании через LLM (OpenAI) и построить вокруг этого:
design doc → сервис → интеграция → хранение → batch/Airflow → мониторинг качества внешней модели.

## Как это связано с основным проектом

- Этот репозиторий — **отдельный** (сдаётся преподавателю).
- Интеграция с продуктом делается **по HTTP**:
  - Mini App backend (в основном проекте) вызывает `moderation-service` перед `/api/squads/create` и `/api/squads/update`.
  - Админ‑контур (Telegram‑бот) позволяет разбирать очередь `review` и давать “истину” для метрик качества.

## Что здесь будет (по компонентам модуля)

1) Design Doc (business/DS/pilot): `docs/ML_SYSTEM_DESIGN_DOC.md`  
2) Архитектура + ADR + C4 + NFR: `docs/adr/`, `docs/c4/`  
3) Online moderation service (REST + Docker + CI/CD): `service/`  
4) Storage (Postgres + S3): миграции/описания в `docs/` + код в `service/`/`batch/`  
5) Batch/Airflow + backfill: `batch/`  
6) Мониторинг и алертинг (ops + качество LLM): `docs/MONITORING.md` + инфраструктура в `infra/`  

## Быстрый обзор API (черновик)

OpenAPI‑спека: `spec/openapi.yaml`

Эндпоинты:
- `GET /health` — healthcheck
- `POST /moderate` — модерация текста → `allow | block | review` + категории + версии policy/prompt
- `GET /metrics` — метрики Prometheus

Примечание: если задан `OPENAI_API_KEY`, сервис использует OpenAI Chat Completions для классификации. Если ключ не задан, используется stub‑классификатор (возвращает `allow`).

## Локальный запуск

### Вариант A (рекомендуется): через `uv`

```bash
uv venv
uv pip install -e ".[dev]"
uvicorn service.main:app --reload --port 8000
```

### Вариант B: через `pip`

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn service.main:app --reload --port 8000
```

Проверка:

```bash
curl -s http://localhost:8000/health
```

## Тесты и линтеры

```bash
pytest
black --check .
isort --check-only .
flake8
pylint src service tests
mypy src service tests
```

## Docker image (GHCR)

CI собирает и пушит image в GitHub Container Registry:
- `ghcr.io/yarstar12/carcase-ai-moderation-mlprod:latest`
- `ghcr.io/yarstar12/carcase-ai-moderation-mlprod:sha-<...>`

Шаблон деплоя на удалённый сервер: `infra/deploy/README.md`

## Структура проекта (Clean Architecture)

- `src/carcase_ai_moderation/domain/` — доменные сущности
- `src/carcase_ai_moderation/application/` — бизнес‑логика, policy, сервис модерации
- `src/carcase_ai_moderation/infrastructure/` — адаптеры (классификаторы, внешние интеграции)
- `service/` — REST‑слой (FastAPI)
- `batch/` — batch‑задачи и Airflow (в следующих итерациях)
- `infra/` — инфраструктура (в следующих итерациях)

## Локальные секреты

Секреты в репозиторий не коммитим. Пример переменных: `.env.example`

## Postgres audit log (moderation_events)

Чтобы писать аудит решений в Postgres:
1) применить `infra/postgres/schema.sql`
2) задать `DATABASE_URL` и `EVENT_STORE_ENABLED=1`

Если `EVENT_STORE_ENABLED=0`, сервис работает без БД и просто возвращает решение.

## Batch: daily report → S3

Команда (пишет отчёт в S3 по данным из Postgres):

```bash
python -m carcase_ai_moderation.batch.daily_report --run-date 2026-02-26
```

Нужные переменные окружения:
- `DATABASE_URL`
- `S3_ENDPOINT_URL` (для MinIO)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `S3_BUCKET`

## Quality evaluation: validation dataset (offline)

Помимо human truth из очереди `review`, качество внешней LLM контролируется на фиксированном validation dataset (golden set):
- full‑набор (тысячи/десятки тысяч примеров) прогоняется периодически;
- smoke‑набор (сотни примеров) используется как быстрый регрессионный тест.

Подход описан в:
- `docs/QUALITY_EVALUATION.md`
- `docs/MONITORING.md`
- `docs/DATA_MODEL.md` (S3 ключи датасета и отчётов)

Команда evaluation (пример smoke):

```bash
python -m carcase_ai_moderation.batch.validation_evaluate --run-date 2026-02-26 --dataset-version v1 --dataset-kind smoke --require-openai
```
