# Мониторинг и оповещения (Prometheus + Grafana + Alertmanager)

Содержимое папки — минимальный шаблон инфраструктуры мониторинга:
- Prometheus собирает метрики сервиса модерации (`/metrics`)
- Grafana визуализирует
- Alertmanager отправляет уведомления в Telegram через сервис‑приёмник вебхуков

## Быстрый старт (локально)

```bash
cd infra/monitoring
cp .env.example .env
docker compose up -d --build
```

Интерфейсы:
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Grafana: `http://localhost:3000`

## Настройка цели для сбора метрик

По умолчанию Prometheus ожидает сервис по имени `moderation-service:8000`.
Если сервис запущен в другом месте — измените `prometheus/prometheus.yml`.
