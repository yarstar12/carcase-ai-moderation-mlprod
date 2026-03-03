# Monitoring & Alerting (ops + качество LLM)

Цель мониторинга:
- быстро ловить инциденты online‑сервиса (latency/errors);
- отслеживать деградации качества внешней LLM (через validation dataset и human truth);
- контролировать дрейф входных данных/выходов системы (PSI/CSI‑прокси);
- держать расходы под контролем.

## 1) Источники метрик

### Online (Prometheus scrape)
Сервис модерации отдаёт `/metrics`:
- `moderation_requests_total{decision,field,action}`
- `moderation_request_latency_seconds` (histogram)

Prometheus скрейпит `/metrics`, Grafana визуализирует.

### Batch (S3 + Pushgateway)
Batch‑джобы (Airflow) формируют дневные агрегаты:
- отчёт `reports/daily/{YYYY-MM-DD}.json` в S3/MinIO;
- агрегаты могут пушиться в Prometheus через Pushgateway (для графиков и алертов).

### Quality evaluation (validation dataset)
Отдельная batch‑задача прогоняет validation dataset (golden set) через тот же пайплайн модерации и считает качество как регрессионный тест.
Подход и формат датасета описаны в `docs/QUALITY_EVALUATION.md`.

## 2) Ключевые метрики

### Ops (online)
- latency p95/p99 по `moderation_request_latency_seconds`
- error/timeout rate (по расширению метрик при необходимости)
- request rate / throughput

### Качество (validation dataset, offline)
- `precision_block`, `recall_block`, `f1_block` на full‑наборе (периодически)
- регрессионная проверка на smoke‑наборе (часто)
- доля критичных ошибок: `expected=block`, `predicted=allow`

### Качество (human truth, offline)
- `override_rate` (как часто финал человека ≠ решению модели)
- `review_approve_rate` / `review_reject_rate`
- SLA очереди `review` (время до решения)

### Дрейф (offline)
- PSI по распределению решений vs baseline окно
- CSI‑прокси (например по корзинам длины текста) vs baseline окно

### Стоимость (online/offline)
- calls/day, tokens/day (если логируем), rate limit hits
- hard cap по числу LLM‑запросов и алерты на 70–80% лимита

## 3) Алерты (минимум)
- Moderation service down
- p95 latency выше порога длительное время
- доля `review` выросла резко (риск перегруза ручной очереди и ухудшения UX)
- деградация качества на validation dataset (падение метрик ниже порога или сильная просадка относительно baseline)
- PSI/CSI выше порога (аномальное изменение входа/выхода)

## Runbook (минимум)
1) Проверить жив ли сервис и БД/S3
2) Включить “safe mode” (feature flag) в продукте
3) Проверить отчёты batch за сутки и результаты validation evaluation
4) При необходимости откатить `policy/prompt/model` по версиям или временно увеличить долю `review`

## Инфраструктура (минимальный шаблон)

Docker Compose для Prometheus + Grafana + Alertmanager лежит в `infra/monitoring/`.
