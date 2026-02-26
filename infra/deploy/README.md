# Deploy (push model) — template

Цель: деплой сервиса на удалённую Linux VM по схеме “push” из GitHub Actions:
после пуша в `main` собираем Docker image → пушим в registry → по SSH выполняем `docker compose pull && up -d`.

## 1) На сервере (один раз)

1) Установить Docker + Docker Compose plugin.
2) Создать директорию, например `/opt/carcase-moderation/` и положить туда:
   - `infra/deploy/docker-compose.yml` (переименовать/скопировать как есть)
   - `.env` (по образцу `.env.example`, но с реальными значениями)
3) Войти в GHCR (если image приватный):

```bash
docker login ghcr.io
```

## 2) GitHub Secrets

В репозитории добавить secrets:
- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY` (private key)
- `DEPLOY_PATH` (например `/opt/carcase-moderation`)

## 3) Команда деплоя

Workflow выполняет на сервере:

```bash
cd "$DEPLOY_PATH"
docker compose pull
docker compose up -d
```

