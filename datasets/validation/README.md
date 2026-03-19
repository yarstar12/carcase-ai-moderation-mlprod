# Валидационный датасет (JSONL) — формат

Эта папка содержит небольшие **примерные** валидационные датасеты (эталонный набор), чтобы показать формат.

В рабочем окружении полный датасет хранится в S3/MinIO по ключам вида:
- `datasets/validation/{dataset_version}.jsonl`
- `datasets/validation/{dataset_version}.smoke.jsonl`

Примечание: по умолчанию Git хранит только короткий набор (`smoke`), а полный набор (`full`) игнорируется и должен лежать в S3/MinIO.

## Формат

Один JSON‑объект на строку (**JSONL**). Минимальные поля:
- `id` — уникальный идентификатор примера
- `dataset_version` — например `v1`
- `field` — `squad_name | squad_description`
- `action` — `create | update`
- `text` — входной текст
- `expected_categories` — список категорий (может быть пустым)
- `expected_decision` — `allow | block | review`
- `source` — `synthetic | review_human_truth | other`
- `notes` — опционально

## Категории (v1)

`expected_categories` содержит одну или несколько категорий из списка:
- `profanity_insult_harassment`
- `hate_extremism_terror`
- `sexual`
- `sexual_minors`
- `self_harm_instructions`
- `violence_threats`
- `spam_ads_scam`
- `pii_doxxing`

## Про плейсхолдеры

Некоторые примеры в `v1.smoke.jsonl` намеренно используют плейсхолдеры (например `[REDACTED_...]`), чтобы не коммитить явный вредоносный контент в репозиторий.
Это “каркас”: позже можно заменить плейсхолдеры на более реалистичные примеры, сохранив корректность формата.

## Генерация синтетического датасета

Чтобы сгенерировать более крупный синтетический датасет (как стартовую точку для полного набора):

```bash
python -m carcase_ai_moderation.batch.validation_dataset_generate \
  --dataset-version v1 \
  --dataset-kind full \
  --total 5000 \
  --seed 1 \
  --out-path datasets/validation/v1.jsonl
```

## Загрузка в S3/MinIO

Чтобы загрузить локальный JSONL‑файл в S3/MinIO:

```bash
python -m carcase_ai_moderation.batch.validation_dataset_upload \
  --dataset-version v1 \
  --dataset-kind full \
  --dataset-path datasets/validation/v1.jsonl
```

Нужные переменные окружения:
- `S3_ENDPOINT_URL` (опционально, для MinIO)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `S3_BUCKET`
