# CARCASE — сервис ИИ‑модерации

Репозиторий содержит отдельный сервис модерации пользовательского текста для продукта **CARCASE ARENA** (Telegram Mini App).

Сервис проверяет название и описание клана при создании/редактировании, чтобы:
- не допускать публикации нарушений в публичных рейтингах;
- автоматизировать модерацию и снизить расходы на ручную проверку;
- контролировать качество внешней языковой модели (OpenAI) через оффлайн‑оценку и мониторинг.

## Связь с продуктом

Интеграция с продуктом делается по HTTP:
- бэкенд продукта вызывает `moderation-service` перед созданием/изменением клана;
- админ‑контур (Telegram‑бот) разбирает случаи `review` и (при необходимости) проводит выборочный аудит авто‑решений.

## Состав репозитория

- `docs/ML_SYSTEM_DESIGN_DOC.md` — дизайн‑документ системы машинного обучения (бизнес, часть по данным, пилот, внедрение)
- `docs/adr/` — ADR (архитектурные решения)
- `docs/c4/` — схемы C4
- `service/` — HTTP API (FastAPI)
- `src/carcase_ai_moderation/` — домен/бизнес‑логика/инфраструктурные адаптеры
- `spec/openapi.yaml` — OpenAPI‑контракт
- `infra/` — шаблоны инфраструктуры (деплой, Airflow, мониторинг)

## API (кратко)

OpenAPI‑контракт: `spec/openapi.yaml`

Эндпоинты:
- `GET /health` — проверка работоспособности
- `POST /moderate` — модерация текста → `allow | block | review` + категории + версии policy/prompt/model
- `GET /metrics` — метрики Prometheus

Примечание: если задан `OPENAI_API_KEY`, сервис использует API OpenAI (Chat Completions) для классификации. Если ключ не задан, используется классификатор‑заглушка (всегда возвращает `allow`).

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

### Фиксация зависимостей (`uv.lock`)

Зависимости фиксируются через `uv.lock`:
- локально: `uv lock --all-extras`
- в CI: workflow `lock` (запуск вручную) генерирует/обновляет и коммитит `uv.lock`.

## Проверка качества кода

```bash
pytest
black --check .
isort --check-only .
flake8
pylint src service tests
mypy src service tests
```

## Docker‑образ (GHCR)

CI собирает и публикует образ в контейнерный реестр GitHub (GHCR):
- `ghcr.io/yarstar12/carcase-ai-moderation-mlprod:latest`
- `ghcr.io/yarstar12/carcase-ai-moderation-mlprod:sha-<...>`

Шаблон деплоя на удалённый сервер (push‑модель): `infra/deploy/README.md`

## Структура проекта (чистая архитектура)

- `src/carcase_ai_moderation/domain/` — доменные сущности
- `src/carcase_ai_moderation/application/` — бизнес‑логика (policy, правила, сервис модерации)
- `src/carcase_ai_moderation/infrastructure/` — адаптеры (OpenAI, Postgres, S3)
- `service/` — HTTP‑слой (FastAPI)
- `infra/` — инфраструктура (Airflow, мониторинг, деплой)

## Секреты и переменные окружения

Секреты в репозиторий не коммитим. Пример переменных: `.env.example`.

## Аудит в Postgres (moderation_events)

Чтобы писать аудит решений в Postgres:
1) применить `infra/postgres/schema.sql`
2) задать `DATABASE_URL` и `EVENT_STORE_ENABLED=1`

Если `EVENT_STORE_ENABLED=0`, сервис работает без БД и просто возвращает решение.

## Пакетные задачи: ежедневный отчёт → S3

Команда (пишет отчёт в S3 по данным из Postgres):

```bash
python -m carcase_ai_moderation.batch.daily_report --run-date 2026-02-26
```

Нужные переменные окружения:
- `DATABASE_URL`
- `S3_ENDPOINT_URL` (для MinIO)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `S3_BUCKET`

## Оффлайн‑оценка качества на валидационном датасете

Качество внешней языковой модели контролируется на фиксированном валидационном датасете (эталонном наборе примеров):
- полный набор (`full`, тысячи/десятки тысяч примеров) прогоняется периодически;
- короткий набор (`smoke`, сотни примеров) используется как быстрый регрессионный тест.

Подход описан в:
- `docs/QUALITY_EVALUATION.md`
- `docs/MONITORING.md`
- `docs/DATA_MODEL.md` (ключи S3 для датасетов и отчётов)

Команда оценки (пример `smoke`):

```bash
python -m carcase_ai_moderation.batch.validation_evaluate \
  --run-date 2026-02-26 \
  --dataset-version v1 \
  --dataset-kind smoke \
  --require-openai
```
