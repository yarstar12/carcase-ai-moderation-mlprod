from __future__ import annotations

import argparse
import logging
from os import getenv
from pathlib import Path

from carcase_ai_moderation.batch.validation_evaluate import build_dataset_s3_key
from carcase_ai_moderation.infrastructure.s3_client import S3Client, S3Config

LOGGER = logging.getLogger(__name__)


class BatchError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = getenv(name)
    if not value:
        raise BatchError(f"Missing required env var: {name}")
    return value


def _s3_client_from_env() -> S3Client:
    return S3Client(
        S3Config(
            endpoint_url=getenv("S3_ENDPOINT_URL"),
            access_key=_require_env("S3_ACCESS_KEY"),
            secret_key=_require_env("S3_SECRET_KEY"),
            bucket=_require_env("S3_BUCKET"),
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload a local validation dataset (JSONL) to S3.")
    parser.add_argument("--dataset-version", default="v1", help="Validation dataset version.")
    parser.add_argument(
        "--dataset-kind",
        default="smoke",
        choices=("smoke", "full"),
        help="Which dataset key to upload to (smoke or full).",
    )
    parser.add_argument(
        "--dataset-path",
        required=True,
        help="Local dataset path (JSONL).",
    )
    parser.add_argument(
        "--datasets-prefix",
        default="datasets/validation",
        help="S3 prefix for validation datasets.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite object if it already exists in S3.",
    )
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        raise BatchError("dataset-path does not exist")
    if not dataset_path.is_file():
        raise BatchError("dataset-path must be a file")

    body = dataset_path.read_bytes()
    if not body.strip():
        raise BatchError("dataset-path is empty")

    s3_key = build_dataset_s3_key(
        datasets_prefix=args.datasets_prefix,
        dataset_version=args.dataset_version,
        dataset_kind=args.dataset_kind,
    )

    s3_client = _s3_client_from_env()
    if not args.overwrite and s3_client.object_exists(key=s3_key):
        LOGGER.info("Dataset already exists in S3, skipping: %s", s3_key)
        return 0

    s3_client.put_bytes(key=s3_key, body=body, content_type="application/x-ndjson")
    LOGGER.info("Uploaded dataset to S3: s3://%s/%s", s3_client.config.bucket, s3_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
