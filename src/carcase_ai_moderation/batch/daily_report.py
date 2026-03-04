from __future__ import annotations

import argparse
import importlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from os import getenv
from typing import Any, cast

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from carcase_ai_moderation.application.drift import normalize_counts, psi
from carcase_ai_moderation.infrastructure.s3_client import S3Client, S3Config

LOGGER = logging.getLogger(__name__)


class BatchError(RuntimeError):
    pass


def _import_psycopg() -> Any:
    try:
        return importlib.import_module("psycopg")
    except ModuleNotFoundError as exc:
        raise BatchError("psycopg is required for batch jobs") from exc


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BatchError("run-date must be in YYYY-MM-DD format") from exc


def _normalize_prefix(prefix: str) -> str:
    trimmed = prefix.strip().strip("/")
    if not trimmed:
        raise BatchError("s3-prefix must not be empty")
    return trimmed


@dataclass(frozen=True, slots=True)
class ReportWindow:
    run_date: date
    start_utc: datetime
    end_utc: datetime
    baseline_start_utc: datetime
    baseline_end_utc: datetime
    lookback_days: int

    @classmethod
    def for_run_date(cls, *, run_date: date, lookback_days: int) -> "ReportWindow":
        if lookback_days <= 0:
            raise BatchError("lookback-days must be positive")

        start = datetime(run_date.year, run_date.month, run_date.day, tzinfo=UTC)
        end = start + timedelta(days=1)
        baseline_end = start
        baseline_start = baseline_end - timedelta(days=lookback_days)
        return cls(
            run_date=run_date,
            start_utc=start,
            end_utc=end,
            baseline_start_utc=baseline_start,
            baseline_end_utc=baseline_end,
            lookback_days=lookback_days,
        )


@dataclass(frozen=True, slots=True)
class Aggregates:
    total: int
    decisions: dict[str, int]
    categories: dict[str, int]
    text_length_buckets: dict[str, int]


@dataclass(frozen=True, slots=True)
class ReportMetrics:
    total: int
    review_rate: float
    block_rate: float
    classifier_error_rate: float
    psi_decisions_vs_baseline: float | None
    csi_text_length_vs_baseline: float | None


def _length_bucket_sql() -> str:
    return """
        case
            when length(text_raw) < 10 then 'lt_10'
            when length(text_raw) < 20 then 'lt_20'
            when length(text_raw) < 30 then 'lt_30'
            when length(text_raw) < 50 then 'lt_50'
            when length(text_raw) < 100 then 'lt_100'
            else 'gte_100'
        end
    """


def _fetch_total(cur: Any, *, start_utc: datetime, end_utc: datetime) -> int:
    cur.execute(
        """
        select count(*)::bigint
        from moderation_events
        where created_at >= %(s)s and created_at < %(e)s
        """,
        {"s": start_utc, "e": end_utc},
    )
    row = cur.fetchone()
    if not row:
        return 0
    return int(row[0])


def _fetch_decisions(cur: Any, *, start_utc: datetime, end_utc: datetime) -> dict[str, int]:
    cur.execute(
        """
        select decision, count(*)::bigint
        from moderation_events
        where created_at >= %(s)s and created_at < %(e)s
        group by decision
        """,
        {"s": start_utc, "e": end_utc},
    )
    return {str(decision): int(count) for decision, count in cur.fetchall()}


def _fetch_categories(cur: Any, *, start_utc: datetime, end_utc: datetime) -> dict[str, int]:
    cur.execute(
        """
        select category, count(*)::bigint
        from moderation_events
        cross join lateral jsonb_array_elements_text(categories) as category
        where created_at >= %(s)s and created_at < %(e)s
        group by category
        """,
        {"s": start_utc, "e": end_utc},
    )
    return {str(category): int(count) for category, count in cur.fetchall()}


def _fetch_text_length_buckets(
    cur: Any, *, start_utc: datetime, end_utc: datetime
) -> dict[str, int]:
    cur.execute(
        f"""
        select {_length_bucket_sql()} as bucket, count(*)::bigint
        from moderation_events
        where created_at >= %(s)s and created_at < %(e)s
        group by bucket
        """,
        {"s": start_utc, "e": end_utc},
    )
    return {str(bucket): int(count) for bucket, count in cur.fetchall()}


def fetch_aggregates(*, database_url: str, start_utc: datetime, end_utc: datetime) -> Aggregates:
    psycopg = _import_psycopg()
    psycopg_error = cast(type[BaseException], psycopg.Error)

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                total = _fetch_total(cur, start_utc=start_utc, end_utc=end_utc)
                decisions = _fetch_decisions(cur, start_utc=start_utc, end_utc=end_utc)
                categories = _fetch_categories(cur, start_utc=start_utc, end_utc=end_utc)
                text_length_buckets = _fetch_text_length_buckets(
                    cur, start_utc=start_utc, end_utc=end_utc
                )
    except psycopg_error as exc:
        raise BatchError("Failed to read from Postgres") from exc

    return Aggregates(
        total=total,
        decisions=decisions,
        categories=categories,
        text_length_buckets=text_length_buckets,
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def build_s3_key(*, s3_prefix: str, run_date: date) -> str:
    prefix = _normalize_prefix(s3_prefix)
    return f"{prefix}/{run_date.isoformat()}.json"


def compute_metrics(*, current: Aggregates, baseline: Aggregates) -> ReportMetrics:
    review_count = current.decisions.get("review", 0)
    block_count = current.decisions.get("block", 0)
    classifier_error_count = current.categories.get("classifier_error", 0)

    baseline_decisions = normalize_counts(baseline.decisions)
    current_decisions = normalize_counts(current.decisions)
    baseline_lengths = normalize_counts(baseline.text_length_buckets)
    current_lengths = normalize_counts(current.text_length_buckets)

    psi_decisions = (
        psi(expected=baseline_decisions, actual=current_decisions) if baseline_decisions else None
    )
    csi_lengths = (
        psi(expected=baseline_lengths, actual=current_lengths) if baseline_lengths else None
    )

    return ReportMetrics(
        total=current.total,
        review_rate=_safe_rate(review_count, current.total),
        block_rate=_safe_rate(block_count, current.total),
        classifier_error_rate=_safe_rate(classifier_error_count, current.total),
        psi_decisions_vs_baseline=psi_decisions,
        csi_text_length_vs_baseline=csi_lengths,
    )


def build_report(
    *,
    window: ReportWindow,
    current: Aggregates,
    baseline: Aggregates,
    metrics: ReportMetrics | None = None,
) -> dict[str, object]:
    report_metrics = metrics or compute_metrics(current=current, baseline=baseline)

    return {
        "run_date": window.run_date.isoformat(),
        "window": {
            "start_utc": window.start_utc.isoformat(),
            "end_utc": window.end_utc.isoformat(),
            "baseline_start_utc": window.baseline_start_utc.isoformat(),
            "baseline_end_utc": window.baseline_end_utc.isoformat(),
            "lookback_days": window.lookback_days,
        },
        "counts": {
            "total": current.total,
            "decisions": dict(sorted(current.decisions.items())),
            "categories": dict(sorted(current.categories.items())),
            "text_length_buckets": dict(sorted(current.text_length_buckets.items())),
        },
        "rates": {
            "review_rate": report_metrics.review_rate,
            "block_rate": report_metrics.block_rate,
            "classifier_error_rate": report_metrics.classifier_error_rate,
        },
        "drift": {
            "psi_decisions_vs_baseline": report_metrics.psi_decisions_vs_baseline,
            "csi_text_length_vs_baseline": report_metrics.csi_text_length_vs_baseline,
        },
        "quality": {
            "status": "pending_labels",
            "note": "Quality metrics require human labels from the review workflow.",
        },
    }


def push_metrics(*, pushgateway_url: str, metrics: ReportMetrics) -> None:
    registry = CollectorRegistry()

    total = Gauge(
        "moderation_daily_total", "Total moderation events for the day", registry=registry
    )
    review_rate = Gauge(
        "moderation_daily_review_rate", "Daily share of review decisions", registry=registry
    )
    block_rate = Gauge(
        "moderation_daily_block_rate", "Daily share of block decisions", registry=registry
    )
    classifier_error_rate = Gauge(
        "moderation_daily_classifier_error_rate",
        "Daily share of classifier errors (fallback to review)",
        registry=registry,
    )
    psi_decisions = Gauge(
        "moderation_daily_psi_decisions",
        "PSI for decision distribution vs baseline window",
        registry=registry,
    )
    csi_text_length = Gauge(
        "moderation_daily_csi_text_length",
        "CSI (PSI-based) for text length buckets vs baseline window",
        registry=registry,
    )

    total.set(metrics.total)
    review_rate.set(metrics.review_rate)
    block_rate.set(metrics.block_rate)
    classifier_error_rate.set(metrics.classifier_error_rate)
    if metrics.psi_decisions_vs_baseline is not None:
        psi_decisions.set(metrics.psi_decisions_vs_baseline)
    if metrics.csi_text_length_vs_baseline is not None:
        csi_text_length.set(metrics.csi_text_length_vs_baseline)

    push_to_gateway(
        pushgateway_url,
        job="moderation_daily_report",
        registry=registry,
    )


def _require_env(name: str) -> str:
    value = getenv(name)
    if not value:
        raise BatchError(f"Missing required env var: {name}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate daily moderation report and upload to S3."
    )
    parser.add_argument("--run-date", required=True, help="Report date in YYYY-MM-DD (UTC).")
    parser.add_argument("--lookback-days", type=int, default=7, help="Baseline window size.")
    parser.add_argument(
        "--s3-prefix",
        default="reports/daily",
        help="S3 key prefix for reports (default: reports/daily).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite report if it already exists in S3.",
    )
    args = parser.parse_args(argv)

    run_date = _parse_iso_date(args.run_date)
    window = ReportWindow.for_run_date(run_date=run_date, lookback_days=args.lookback_days)
    report_key = build_s3_key(s3_prefix=args.s3_prefix, run_date=run_date)

    database_url = _require_env("DATABASE_URL")
    s3_client = S3Client(
        S3Config(
            endpoint_url=getenv("S3_ENDPOINT_URL"),
            access_key=_require_env("S3_ACCESS_KEY"),
            secret_key=_require_env("S3_SECRET_KEY"),
            bucket=_require_env("S3_BUCKET"),
        )
    )

    if not args.overwrite and s3_client.object_exists(key=report_key):
        LOGGER.info("Report already exists in S3, skipping: %s", report_key)
        return 0

    current = fetch_aggregates(
        database_url=database_url,
        start_utc=window.start_utc,
        end_utc=window.end_utc,
    )
    baseline = fetch_aggregates(
        database_url=database_url,
        start_utc=window.baseline_start_utc,
        end_utc=window.baseline_end_utc,
    )
    metrics = compute_metrics(current=current, baseline=baseline)
    report = build_report(window=window, current=current, baseline=baseline, metrics=metrics)
    s3_client.put_json(key=report_key, payload=report)
    LOGGER.info("Uploaded report to S3: %s", report_key)

    pushgateway_url = getenv("PUSHGATEWAY_URL")
    if pushgateway_url:
        try:
            push_metrics(pushgateway_url=pushgateway_url, metrics=metrics)
        except OSError as exc:
            LOGGER.warning("Failed to push metrics to Pushgateway: %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
