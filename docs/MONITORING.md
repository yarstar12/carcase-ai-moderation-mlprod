# Monitoring & Alerting (ops + качество LLM)

## Ops метрики
- p95 latency, error rate, timeouts
- throughput (requests/min)
- cost proxy: calls/day, tokens/day (если логируем), rate limit hits

## Метрики качества (по human truth)
- precision/recall/F1 на golden set (batch)
- override rate (admin отменил решение)
- доля `review` и нагрузка на модераторов

## Алерты (черновик)
- error rate > N% за 5–10 минут
- p95 latency > X ms
- override rate / review rate ↑ резко (порог + тренд)

## Runbook (минимум)
1) Проверить жив ли сервис и БД/S3
2) Включить “safe mode” (feature flag) в продукте
3) Снять сэмплы событий за период и сравнить с baseline

