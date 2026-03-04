from datetime import date

from carcase_ai_moderation.batch.validation_evaluate import (
    build_dataset_s3_key,
    build_report_s3_key,
)


def test_build_dataset_s3_key_smoke() -> None:
    assert (
        build_dataset_s3_key(
            datasets_prefix="datasets/validation",
            dataset_version="v1",
            dataset_kind="smoke",
        )
        == "datasets/validation/v1.smoke.jsonl"
    )


def test_build_dataset_s3_key_full() -> None:
    assert (
        build_dataset_s3_key(
            datasets_prefix="datasets/validation",
            dataset_version="v1",
            dataset_kind="full",
        )
        == "datasets/validation/v1.jsonl"
    )


def test_build_report_s3_key() -> None:
    assert (
        build_report_s3_key(
            reports_prefix="reports/validation",
            dataset_version="v1",
            dataset_kind="smoke",
            run_date=date(2026, 2, 26),
        )
        == "reports/validation/v1/smoke/2026-02-26.json"
    )
