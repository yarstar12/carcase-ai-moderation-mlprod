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
- `DEPLOY_SSH_KEY_B64` (base64 от приватного SSH-ключа без переводов строк)
- `DEPLOY_PATH` (например `/opt/carcase-moderation`)

Пример получения `DEPLOY_SSH_KEY_B64` локально:

```bash
base64 -i ~/.ssh/carcase_moderation_deploy | tr -d '\n'
```

Для деплоя используется отдельный пользователь сервера, например `deploy`, а не `root`.

## 2.1) Что уже принято в текущем окружении

- deploy user: `deploy`
- deploy path: `/opt/carcase-moderation`
- service domain: `moderation.carcase.store`
- compose file on server: `/opt/carcase-moderation/docker-compose.yml`
- env file on server: `/opt/carcase-moderation/.env`

## 3) Команда деплоя

Workflow GitHub Actions выполняет на сервере:

```bash
cd "$DEPLOY_PATH"
docker compose pull
docker compose up -d
```

## 4) Минимальная проверка после деплоя

На сервере:

```bash
cd /opt/carcase-moderation
docker compose ps
docker compose logs --tail=100
curl http://127.0.0.1:8000/health
```

Снаружи:

```bash
curl https://moderation.carcase.store/health
```

## 5) Что не хранить в GitHub Secrets

Runtime secrets самого сервиса не должны попадать в workflow:
- `OPENAI_API_KEY`
- `DATABASE_URL`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`

Они должны жить в серверном `.env`:
- `/opt/carcase-moderation/.env`
