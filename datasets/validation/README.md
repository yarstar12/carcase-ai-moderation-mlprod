# Validation dataset (JSONL) — how it looks

This folder contains small **example** validation datasets (golden set) to demonstrate the format.

In production, the full datasets are expected to live in S3/MinIO under keys like:
- `datasets/validation/{dataset_version}.jsonl`
- `datasets/validation/{dataset_version}.smoke.jsonl`

## Format

One JSON object per line (**JSONL**). Minimal fields:
- `id` — unique example id
- `dataset_version` — e.g. `v1`
- `field` — `squad_name | squad_description`
- `action` — `create | update`
- `text` — input text
- `expected_categories` — list of categories (can be empty)
- `expected_decision` — `allow | block | review`
- `source` — `synthetic | review_human_truth | other`
- `notes` — optional

## Categories (v1)

Expected categories should be one or more of:
- `profanity_insult_harassment`
- `hate_extremism_terror`
- `sexual`
- `sexual_minors`
- `self_harm_instructions`
- `violence_threats`
- `spam_ads_scam`
- `pii_doxxing`

## Notes on placeholders

Some examples in `v1.smoke.jsonl` intentionally use placeholders (e.g. `[REDACTED_...]`) to avoid committing explicit harmful content.
They are meant as scaffolding: you can replace them later with more realistic examples while keeping the dataset compliant and safe.

## Generate a synthetic dataset

To generate a larger synthetic dataset (for experimentation and as a starting point for a full validation set):

```bash
python -m carcase_ai_moderation.batch.validation_dataset_generate \
  --dataset-version v1 \
  --dataset-kind full \
  --total 5000 \
  --seed 1 \
  --out-path datasets/validation/v1.jsonl
```

Note: full datasets are expected to live in S3/MinIO and are ignored by git by default.

To upload a local JSONL file to S3/MinIO:

```bash
python -m carcase_ai_moderation.batch.validation_dataset_upload \
  --dataset-version v1 \
  --dataset-kind full \
  --dataset-path datasets/validation/v1.jsonl
```

Required env vars:
- `S3_ENDPOINT_URL` (optional, for MinIO)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `S3_BUCKET`
