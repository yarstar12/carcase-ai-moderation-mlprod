from datetime import date, datetime, timezone
from typing import Any, cast

import pytest

from carcase_ai_moderation.batch.daily_report import (
    Aggregates,
    BatchError,
    ReportMetrics,
    ReportWindow,
    build_report,
    build_s3_key,
    main,
    push_metrics,
)


def test_report_window_boundaries_utc() -> None:
    window = ReportWindow.for_run_date(run_date=date(2026, 2, 26), lookback_days=7)
    assert window.start_utc == datetime(2026, 2, 26, tzinfo=timezone.utc)
    assert window.end_utc == datetime(2026, 2, 27, tzinfo=timezone.utc)
    assert window.baseline_end_utc == window.start_utc
    assert window.baseline_start_utc == datetime(2026, 2, 19, tzinfo=timezone.utc)


def test_build_s3_key_normalizes_prefix() -> None:
    key = build_s3_key(s3_prefix="/reports/daily/", run_date=date(2026, 2, 26))
    assert key == "reports/daily/2026-02-26.json"


def test_build_s3_key_rejects_empty_prefix() -> None:
    with pytest.raises(BatchError):
        build_s3_key(s3_prefix=" / ", run_date=date(2026, 2, 26))


def test_build_report_contains_rates_and_drift() -> None:
    window = ReportWindow.for_run_date(run_date=date(2026, 2, 26), lookback_days=7)
    current = Aggregates(
        total=10,
        decisions={"allow": 7, "review": 2, "block": 1},
        categories={"spam_ads_scam": 1, "classifier_error": 1},
        text_length_buckets={"lt_10": 5, "lt_20": 5},
    )
    baseline = Aggregates(
        total=20,
        decisions={"allow": 10, "review": 5, "block": 5},
        categories={"spam_ads_scam": 2},
        text_length_buckets={"lt_10": 10, "lt_20": 10},
    )

    report = build_report(window=window, current=current, baseline=baseline)
    report_any = cast(dict[str, Any], report)
    assert report_any["run_date"] == "2026-02-26"
    rates = cast(dict[str, Any], report_any["rates"])
    assert rates["review_rate"] == 0.2
    assert rates["block_rate"] == 0.1
    assert rates["classifier_error_rate"] == 0.1

    drift = cast(dict[str, Any], report_any["drift"])
    assert drift["psi_decisions_vs_baseline"] is not None
    assert drift["csi_text_length_vs_baseline"] == 0.0


def test_main_skips_if_report_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_BUCKET", "b")

    class DummyS3:
        def __init__(self, _cfg: object) -> None:
            self.put_calls: list[tuple[str, dict[str, object]]] = []

        def object_exists(self, *, key: str) -> bool:
            assert key.endswith("2026-02-26.json")
            return True

        def put_json(self, *, key: str, payload: dict[str, object]) -> None:
            self.put_calls.append((key, payload))

    def fetch_aggregates_stub(*_args: object, **_kwargs: object) -> Aggregates:
        raise AssertionError("fetch_aggregates should not be called when report exists")

    monkeypatch.setattr("carcase_ai_moderation.batch.daily_report.S3Client", DummyS3)
    monkeypatch.setattr(
        "carcase_ai_moderation.batch.daily_report.fetch_aggregates", fetch_aggregates_stub
    )

    assert main(["--run-date", "2026-02-26"]) == 0


def test_main_uploads_report_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_BUCKET", "b")

    class DummyS3:
        def __init__(self, _cfg: object) -> None:
            self.put_calls: list[tuple[str, dict[str, object]]] = []

        def object_exists(self, *, key: str) -> bool:
            assert key.endswith("2026-02-26.json")
            return False

        def put_json(self, *, key: str, payload: dict[str, object]) -> None:
            self.put_calls.append((key, payload))

    calls: list[tuple[datetime, datetime]] = []

    def fetch_aggregates_stub(
        *, database_url: str, start_utc: datetime, end_utc: datetime
    ) -> Aggregates:
        _ = database_url
        calls.append((start_utc, end_utc))
        return Aggregates(
            total=1,
            decisions={"allow": 1},
            categories={},
            text_length_buckets={"lt_10": 1},
        )

    dummy_s3 = DummyS3(object())

    def s3_factory(_cfg: object) -> DummyS3:
        return dummy_s3

    monkeypatch.setattr("carcase_ai_moderation.batch.daily_report.S3Client", s3_factory)
    monkeypatch.setattr(
        "carcase_ai_moderation.batch.daily_report.fetch_aggregates", fetch_aggregates_stub
    )

    assert main(["--run-date", "2026-02-26", "--lookback-days", "7"]) == 0
    assert len(calls) == 2
    assert len(dummy_s3.put_calls) == 1
    key, payload = dummy_s3.put_calls[0]
    assert key == "reports/daily/2026-02-26.json"
    payload_any = cast(dict[str, Any], payload)
    assert payload_any["run_date"] == "2026-02-26"


def test_push_metrics_pushes_to_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def push_stub(*args: object, **kwargs: object) -> None:
        _ = args
        calls.append(dict(kwargs))

    monkeypatch.setattr("carcase_ai_moderation.batch.daily_report.push_to_gateway", push_stub)

    push_metrics(
        pushgateway_url="http://pushgateway:9091",
        report_date=date(2026, 2, 26),
        metrics=ReportMetrics(
            total=1,
            review_rate=0.0,
            block_rate=0.0,
            classifier_error_rate=0.0,
            psi_decisions_vs_baseline=0.0,
            csi_text_length_vs_baseline=0.0,
        ),
    )

    assert calls
    assert calls[0]["grouping_key"] == {"report_date": "2026-02-26"}
