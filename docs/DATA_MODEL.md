# Data model (Postgres + S3) — draft

Цель: обеспечить аудит, воспроизводимость решений и источники данных для оценки качества внешней LLM.

## 1) Postgres (операционные таблицы)

### 1.1 moderation_events
Событие “мы попытались промодерировать текст”.

Минимальные поля:
- `id` (PK)
- `created_at`
- `request_id` (idempotency key)
- `user_id`
- `action` (`create|update`)
- `field` (`squad_name|squad_description`)
- `text_raw` (опционально, зависит от политики хранения)
- `text_norm` (нормализованный текст/хэш)
- `decision` (`allow|block|review`)
- `categories` (jsonb array)
- `reason_short`
- `policy_version`, `prompt_version`, `model`
- `latency_ms`, `provider_error` (если был)

Индексы:
- `(created_at desc)`
- `(user_id, created_at desc)`
- `(decision, created_at desc)`

### 1.2 moderation_review_queue
Очередь ручной модерации (review).

Поля:
- `id` (PK)
- `created_at`
- `status` (`pending|approved|rejected|expired`)
- `review_type` (`squad_create|squad_update`)
- `user_id`
- `payload` (jsonb: name/description/type/tag; для update — new_description)
- `linked_event_id` (FK на moderation_events)

Решение админа:
- `decided_at`
- `decided_by_admin_id`
- `admin_decision` (`approve|reject|edit_approve`)
- `admin_note`
- `admin_payload` (jsonb, если был edit)

### 1.3 (опционально) moderation_labels
Таблица “истины” для golden set, если хочется отделить от очереди.

## 2) S3 (артефакты и отчёты)

### 2.1 Артефакты policy/prompt
Храним версии:
- `policy/{policy_version}.json`
- `prompt/{prompt_version}.txt`

### 2.2 Validation datasets (golden set)
Храним оффлайн‑наборы для оценки качества внешней LLM и регрессионных проверок:
- `datasets/validation/{dataset_version}.jsonl` — full набор
- `datasets/validation/{dataset_version}.smoke.jsonl` — smoke/regression поднабор

Примечание: валидационные наборы не используются в online‑модерации. Они применяются только в evaluation jobs.

### 2.3 Отчёты качества (batch)
- `reports/daily/{YYYY-MM-DD}.json`
- `reports/backfill/{run_id}.json` (опционально, если делаем отдельный backfill‑контур)
- `reports/validation/{dataset_version}/{dataset_kind}/{YYYY-MM-DD}.json` — результаты прогона validation dataset (метрики + версии артефактов)

## 3) Потребности batch

Batch должен уметь:
- собрать/обновлять validation dataset (синтетика + human truth из `review`, после анонимизации)
- посчитать offline метрики на validation dataset (precision/recall/F1, критичные FN, доля `review`)
- посчитать drift метрики (PSI/CSI‑прокси) по прод‑событиям
- записать агрегаты и отчёты в S3/MinIO и (опционально) в Pushgateway
