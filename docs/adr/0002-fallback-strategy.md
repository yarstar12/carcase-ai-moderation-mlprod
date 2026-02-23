# ADR 0002: Fallback strategy (LLM/service outage)

## Status
Proposed

## Options
1) fail-open (разрешаем)
2) fail-closed (блокируем)
3) degrade-to-review (отправляем в ручную очередь)

## Decision (draft)
Для create/update squads UGC: degrade-to-review, с ограничениями по rate limit.

