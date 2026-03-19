# Деплой (push‑модель) — шаблон

Цель: деплой сервиса на удалённую виртуальную машину Linux по модели “push” (деплой инициируется из GitHub Actions):
после пуша в `main` собираем Docker‑образ → публикуем в реестр (GHCR) → по SSH выполняем `docker compose pull` и `docker compose up -d`.

## 1) На сервере (один раз)

1) Установить Docker и плагин Docker Compose.
2) Создать директорию, например `/opt/carcase-moderation/` и положить туда:
   - `infra/deploy/docker-compose.yml` (переименовать/скопировать как есть)
   - `.env` (по образцу `.env.example`, но с реальными значениями)
3) Авторизоваться в GHCR (если образ приватный):

```bash
docker login ghcr.io
```

## 2) Секреты GitHub

В репозитории добавить секреты:
- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY` (приватный ключ)
- `DEPLOY_PATH` (например `/opt/carcase-moderation`)

## 3) Команда деплоя

Workflow GitHub Actions выполняет на сервере:

```bash
cd "$DEPLOY_PATH"
docker compose pull
docker compose up -d
```
