# Integration plan (CARCASE Mini App backend + Telegram bot)

Цель: встроить AI‑модерацию UGC в реальный продуктовый флоу Squads.

## 1) Точки интеграции в Mini App backend

Backend CARCASE ARENA должен вызывать `moderation-service` перед записью в БД:

- `POST /api/squads/create`
  - модерация: `name` (field=`squad_name`) и `description` (field=`squad_description`)
- `POST /api/squads/update`
  - модерация: `description`

## 2) Поведение по решению

### allow
- продолжаем создание/обновление как обычно
- пишем `moderation_event` (decision=allow)

### block
- отклоняем запрос (ошибка валидации на продуктовой стороне)
- пишем `moderation_event` (decision=block)

### review (MVP “максимально качественно, но реализуемо”)
Идея: `review` создаёт **очередь ручной модерации**, чтобы:
- снизить риск FP/FN,
- получать human truth для метрик качества LLM.

Create (новый сквад):
- НЕ списываем Scrap сразу.
- Создаём `squad_pending_create` (или общий `moderation_review_queue`), статус `pending`.
- Пользователь получает нейтральный ответ/сообщение “на проверке”.
- Global Admin принимает решение:
  - approve → транзакционно списываем Scrap и создаём сквад
  - reject → ничего не списываем
  - edit+approve → админ правит текст и создаёт

Update (изменение description):
- Не меняем текущий `squads.description`, пока review не решён.
- Кладём запрос изменения в очередь (pending update).
- По approve применяем обновление, по reject — игнорируем.

## 3) Админ‑контур

Минимум, чтобы удовлетворить модуль:
- список очереди `review` (последние N)
- просмотр деталей (исходный текст, категории, reason, версия policy/prompt, кто запросил)
- кнопки: approve / reject / edit+approve
- запись решения в аудит и связывание с событием LLM

## 4) Feature flags / rollout

Mini App backend должен уметь:
- включать модерацию по проценту трафика (стабильный сплит по user_id)
- быстро выключать (rollback) при инциденте

