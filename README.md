# CARCASE — AI Moderation (ML in Production module)

Учебный проект под требования модуля **ML in Production**: прод‑контур вокруг AI‑модерации UGC в продукте **CARCASE ARENA** (Telegram Mini App).

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

Ключевой endpoint:
- `POST /moderate` → `allow | block | review` + категории + версии policy/prompt

## Локальные секреты

Секреты в репозиторий не коммитим. Пример переменных: `.env.example`

