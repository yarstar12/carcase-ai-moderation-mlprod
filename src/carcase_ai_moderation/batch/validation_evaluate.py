from __future__ import annotations

import argparse
import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from os import getenv

import httpx
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from carcase_ai_moderation.application.ports import TextClassifierPort
from carcase_ai_moderation.application.quality import (
    BlockDecisionMetrics,
    EvaluationRecord,
    MultiLabelMetrics,
    compute_block_decision_metrics,
    compute_multilabel_metrics,
    decision_confusion_matrix,
)
from carcase_ai_moderation.application.service import ModerationService
from carcase_ai_moderation.domain.moderation import Action, Decision, Field, ModerationInput
from carcase_ai_moderation.infrastructure.classifiers import AlwaysAllowClassifier
from carcase_ai_moderation.infrastructure.openai_classifier import OpenAIChatCompletionsClassifier
from carcase_ai_moderation.infrastructure.s3_client import S3Client, S3Config
from carcase_ai_moderation.settings import Settings

LOGGER = logging.getLogger(__name__)


class BatchError(RuntimeError):
    pass


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BatchError("run-date must be in YYYY-MM-DD format") from exc


def _normalize_prefix(prefix: str) -> str:
    trimmed = prefix.strip().strip("/")
    if not trimmed:
        raise BatchError("prefix must not be empty")
    return trimmed


def _require_env(name: str) -> str:
    value = getenv(name)
    if not value:
        raise BatchError(f"Missing required env var: {name}")
    return value


@dataclass(frozen=True, slots=True)
class ValidationExample:
    example_id: str
    dataset_version: str
    field: Field
    action: Action
    text: str
    expected_categories: frozenset[str]
    expected_decision: Decision
    source: str
    notes: str | None


def _parse_example(obj: object) -> ValidationExample:
    if not isinstance(obj, dict):
        raise BatchError("Invalid JSONL: each line must be an object")

    raw_id = obj.get("id")
    dataset_version = obj.get("dataset_version")
    raw_field = obj.get("field")
    raw_action = obj.get("action")
    text = obj.get("text")
    expected_categories = obj.get("expected_categories", [])
    raw_expected_decision = obj.get("expected_decision")
    source = obj.get("source", "unknown")
    notes = obj.get("notes")

    if not isinstance(raw_id, str) or not raw_id.strip():
        raise BatchError("Invalid example: id must be a non-empty string")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise BatchError("Invalid example: dataset_version must be a non-empty string")
    if not isinstance(raw_field, str):
        raise BatchError("Invalid example: field must be a string")
    if not isinstance(raw_action, str):
        raise BatchError("Invalid example: action must be a string")
    if not isinstance(text, str) or not text.strip():
        raise BatchError("Invalid example: text must be a non-empty string")
    if not isinstance(expected_categories, list) or not all(
        isinstance(category, str) for category in expected_categories
    ):
        raise BatchError("Invalid example: expected_categories must be a list of strings")
    if not isinstance(raw_expected_decision, str):
        raise BatchError("Invalid example: expected_decision must be a string")
    if not isinstance(source, str):
        raise BatchError("Invalid example: source must be a string")
    if notes is not None and not isinstance(notes, str):
        raise BatchError("Invalid example: notes must be a string or null")

    return ValidationExample(
        example_id=raw_id,
        dataset_version=dataset_version,
        field=Field(raw_field),
        action=Action(raw_action),
        text=text,
        expected_categories=frozenset(expected_categories),
        expected_decision=Decision(raw_expected_decision),
        source=source,
        notes=notes,
    )


def _looks_redacted(example: ValidationExample) -> bool:
    marker = "[REDACTED_"
    if marker in example.text:
        return True
    if example.notes and "placeholder" in example.notes.lower():
        return True
    return False


def _load_jsonl(text: str) -> list[ValidationExample]:
    examples: list[ValidationExample] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BatchError(f"Invalid JSON at line {line_no}") from exc
        examples.append(_parse_example(obj))
    return examples


def build_dataset_s3_key(*, datasets_prefix: str, dataset_version: str, dataset_kind: str) -> str:
    prefix = _normalize_prefix(datasets_prefix)
    suffix = "smoke.jsonl" if dataset_kind == "smoke" else "jsonl"
    return f"{prefix}/{dataset_version}.{suffix}"


def build_report_s3_key(
    *, reports_prefix: str, dataset_version: str, dataset_kind: str, run_date: date
) -> str:
    prefix = _normalize_prefix(reports_prefix)
    return f"{prefix}/{dataset_version}/{dataset_kind}/{run_date.isoformat()}.json"


def _s3_client_from_env() -> S3Client:
    return S3Client(
        S3Config(
            endpoint_url=getenv("S3_ENDPOINT_URL"),
            access_key=_require_env("S3_ACCESS_KEY"),
            secret_key=_require_env("S3_SECRET_KEY"),
            bucket=_require_env("S3_BUCKET"),
        )
    )


def _load_dataset(
    *,
    dataset_path: str | None,
    datasets_prefix: str,
    dataset_version: str,
    dataset_kind: str,
) -> tuple[list[ValidationExample], dict[str, object]]:
    source: dict[str, object]
    if dataset_path:
        with open(dataset_path, "r", encoding="utf-8") as dataset_file:
            text = dataset_file.read()
        source = {"type": "local", "path": dataset_path}
        return _load_jsonl(text), source

    s3_key = build_dataset_s3_key(
        datasets_prefix=datasets_prefix,
        dataset_version=dataset_version,
        dataset_kind=dataset_kind,
    )
    s3_client = _s3_client_from_env()
    text = s3_client.get_text(key=s3_key)
    source = {"type": "s3", "key": s3_key, "bucket": s3_client.config.bucket}
    return _load_jsonl(text), source


def _select_examples(
    *,
    examples: list[ValidationExample],
    include_redacted: bool,
    max_examples: int | None,
    shuffle: bool,
    sample_seed: int | None,
) -> tuple[list[ValidationExample], int]:
    selected: list[ValidationExample] = []
    skipped_redacted = 0
    for example in examples:
        if (not include_redacted) and _looks_redacted(example):
            skipped_redacted += 1
            continue
        selected.append(example)

    if shuffle:
        random.Random(sample_seed).shuffle(selected)

    if max_examples is not None:
        selected = selected[:max_examples]
    return selected, skipped_redacted


def _evaluate_examples(
    *, examples: list[ValidationExample], moderation_service: ModerationService
) -> tuple[list[EvaluationRecord], float]:
    records: list[EvaluationRecord] = []
    started = time.perf_counter()
    for example in examples:
        result = moderation_service.moderate(
            ModerationInput(
                request_id=f"val:{example.example_id}",
                user_id=1,
                action=example.action,
                field=example.field,
                text=example.text,
            )
        )
        records.append(
            EvaluationRecord(
                example_id=example.example_id,
                expected_decision=example.expected_decision,
                predicted_decision=result.decision,
                expected_categories=example.expected_categories,
                predicted_categories=frozenset(result.categories),
            )
        )
    return records, time.perf_counter() - started


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    elapsed_s: float
    block_metrics: BlockDecisionMetrics
    multilabel_metrics: MultiLabelMetrics
    confusion: dict[str, dict[str, int]]


def _run_evaluation(*, examples: list[ValidationExample], settings: Settings) -> EvaluationResult:
    http_client: httpx.Client | None = None
    if settings.openai_api_key:
        http_client = httpx.Client(timeout=settings.openai_timeout_s)

    try:
        moderation_service = _build_service(settings=settings, http_client=http_client)
        records, elapsed_s = _evaluate_examples(
            examples=examples,
            moderation_service=moderation_service,
        )
    finally:
        if http_client is not None:
            http_client.close()

    return EvaluationResult(
        elapsed_s=elapsed_s,
        block_metrics=compute_block_decision_metrics(records),
        multilabel_metrics=compute_multilabel_metrics(records),
        confusion=decision_confusion_matrix(records),
    )


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    run_date: date
    started_at: datetime
    finished_at: datetime
    elapsed_s: float
    dataset_version: str
    dataset_kind: str
    examples_total: int
    examples_evaluated: int
    examples_skipped_redacted: int
    dataset_source: dict[str, object]


def _build_report(
    *,
    ctx: EvaluationContext,
    settings: Settings,
    block_metrics: BlockDecisionMetrics,
    multilabel_metrics: MultiLabelMetrics,
    confusion: dict[str, dict[str, int]],
) -> dict[str, object]:
    return {
        "run_date": ctx.run_date.isoformat(),
        "started_at_utc": ctx.started_at.isoformat(),
        "finished_at_utc": ctx.finished_at.isoformat(),
        "elapsed_seconds": ctx.elapsed_s,
        "dataset": {
            "dataset_version": ctx.dataset_version,
            "dataset_kind": ctx.dataset_kind,
            "examples_total": ctx.examples_total,
            "examples_evaluated": ctx.examples_evaluated,
            "examples_skipped_redacted": ctx.examples_skipped_redacted,
            "source": ctx.dataset_source,
        },
        "versions": {
            "policy_version": settings.policy.policy_version,
            "prompt_version": settings.policy.prompt_version,
            "openai_model": settings.openai_model if settings.openai_api_key else None,
            "openai_base_url": settings.openai_base_url if settings.openai_api_key else None,
        },
        "metrics": {
            "accuracy": block_metrics.accuracy,
            "review_rate": block_metrics.review_rate,
            "allow_rate": block_metrics.allow_rate,
            "block_rate": block_metrics.block_rate,
            "precision_block": block_metrics.precision_block,
            "recall_block_strict": block_metrics.recall_block_strict,
            "recall_block_safe": block_metrics.recall_block_safe,
            "f1_block": block_metrics.f1_block,
            "critical_fn_rate": block_metrics.critical_fn_rate,
            "categories_micro_precision": multilabel_metrics.micro_precision,
            "categories_micro_recall": multilabel_metrics.micro_recall,
            "categories_micro_f1": multilabel_metrics.micro_f1,
        },
        "decisions": {
            "confusion_matrix": confusion,
        },
        "categories": {
            "per_category": {
                category: {
                    "tp": category_metrics.true_positives,
                    "fp": category_metrics.false_positives,
                    "fn": category_metrics.false_negatives,
                    "precision": category_metrics.precision,
                    "recall": category_metrics.recall,
                    "f1": category_metrics.f1_score,
                }
                for category, category_metrics in multilabel_metrics.per_category.items()
            }
        },
    }


def _build_service(*, settings: Settings, http_client: httpx.Client | None) -> ModerationService:
    classifier: TextClassifierPort
    if settings.openai_api_key:
        classifier = OpenAIChatCompletionsClassifier(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_s=settings.openai_timeout_s,
            http_client=http_client,
        )
    else:
        classifier = AlwaysAllowClassifier()

    return ModerationService(policy=settings.policy, classifier=classifier)


def _push_metrics(
    *,
    pushgateway_url: str,
    dataset_version: str,
    dataset_kind: str,
    block_metrics: BlockDecisionMetrics,
    multilabel_metrics: MultiLabelMetrics,
) -> None:
    registry = CollectorRegistry()

    total = Gauge(
        "moderation_validation_total", "Number of evaluated validation examples", registry=registry
    )
    precision_block = Gauge(
        "moderation_validation_precision_block", "Precision for BLOCK decision", registry=registry
    )
    recall_block_strict = Gauge(
        "moderation_validation_recall_block_strict",
        "Recall for BLOCK decision (strict: predicted=block)",
        registry=registry,
    )
    recall_block_safe = Gauge(
        "moderation_validation_recall_block_safe",
        "Recall for expected BLOCK with safe outcome (predicted!=allow)",
        registry=registry,
    )
    f1_block = Gauge(
        "moderation_validation_f1_block", "F1 for BLOCK decision (strict)", registry=registry
    )
    critical_fn_rate = Gauge(
        "moderation_validation_critical_fn_rate",
        "Share of expected BLOCK predicted as ALLOW",
        registry=registry,
    )
    review_rate = Gauge(
        "moderation_validation_review_rate", "Share of REVIEW decisions", registry=registry
    )
    micro_precision = Gauge(
        "moderation_validation_micro_precision_categories",
        "Micro-averaged precision over categories",
        registry=registry,
    )
    micro_recall = Gauge(
        "moderation_validation_micro_recall_categories",
        "Micro-averaged recall over categories",
        registry=registry,
    )

    total.set(block_metrics.total)
    precision_block.set(block_metrics.precision_block)
    recall_block_strict.set(block_metrics.recall_block_strict)
    recall_block_safe.set(block_metrics.recall_block_safe)
    f1_block.set(block_metrics.f1_block)
    critical_fn_rate.set(block_metrics.critical_fn_rate)
    review_rate.set(block_metrics.review_rate)
    micro_precision.set(multilabel_metrics.micro_precision)
    micro_recall.set(multilabel_metrics.micro_recall)

    push_to_gateway(
        pushgateway_url,
        job="moderation_validation_evaluate",
        registry=registry,
        grouping_key={
            "dataset_version": dataset_version,
            "dataset_kind": dataset_kind,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate moderation quality on a validation dataset (golden set)."
    )
    parser.add_argument("--run-date", required=True, help="Run date in YYYY-MM-DD (UTC).")
    parser.add_argument("--dataset-version", default="v1", help="Validation dataset version.")
    parser.add_argument(
        "--dataset-kind",
        default="smoke",
        choices=("smoke", "full"),
        help="Which dataset to evaluate (smoke or full).",
    )
    parser.add_argument(
        "--dataset-path",
        default=None,
        help="Local dataset path (JSONL). If omitted, dataset is loaded from S3.",
    )
    parser.add_argument(
        "--datasets-prefix",
        default="datasets/validation",
        help="S3 prefix for validation datasets.",
    )
    parser.add_argument(
        "--reports-prefix",
        default="reports/validation",
        help="S3 prefix for validation evaluation reports.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite report if it already exists in S3.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Optional cap on number of evaluated examples (cost control).",
    )
    parser.add_argument(
        "--include-redacted",
        action="store_true",
        help="Include examples containing [REDACTED_*] placeholders in evaluation.",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle filtered examples before applying max_examples.",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible shuffling.",
    )
    parser.add_argument(
        "--require-openai",
        action="store_true",
        help="Fail if OPENAI_API_KEY is not set (to avoid evaluating stub classifier).",
    )
    args = parser.parse_args(argv)

    started_at = datetime.now(tz=UTC)
    run_date = _parse_iso_date(args.run_date)

    settings = Settings.from_env()
    if args.require_openai and not settings.openai_api_key:
        raise BatchError("OPENAI_API_KEY is required for this evaluation run")

    examples, dataset_source = _load_dataset(
        dataset_path=args.dataset_path,
        datasets_prefix=args.datasets_prefix,
        dataset_version=args.dataset_version,
        dataset_kind=args.dataset_kind,
    )
    selected, skipped_redacted = _select_examples(
        examples=examples,
        include_redacted=args.include_redacted,
        max_examples=args.max_examples,
        shuffle=args.shuffle,
        sample_seed=args.sample_seed,
    )

    evaluation = _run_evaluation(examples=selected, settings=settings)

    finished_at = datetime.now(tz=UTC)
    ctx = EvaluationContext(
        run_date=run_date,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_s=evaluation.elapsed_s,
        dataset_version=args.dataset_version,
        dataset_kind=args.dataset_kind,
        examples_total=len(examples),
        examples_evaluated=len(selected),
        examples_skipped_redacted=skipped_redacted,
        dataset_source=dataset_source,
    )
    report = _build_report(
        ctx=ctx,
        settings=settings,
        block_metrics=evaluation.block_metrics,
        multilabel_metrics=evaluation.multilabel_metrics,
        confusion=evaluation.confusion,
    )

    report_s3_key = build_report_s3_key(
        reports_prefix=args.reports_prefix,
        dataset_version=args.dataset_version,
        dataset_kind=args.dataset_kind,
        run_date=run_date,
    )

    if args.dataset_path:
        LOGGER.info(
            "Dataset loaded from local path; report will still be written to S3: %s",
            report_s3_key,
        )

    s3_client = _s3_client_from_env()

    if not args.overwrite and s3_client.object_exists(key=report_s3_key):
        LOGGER.info("Report already exists in S3, skipping: %s", report_s3_key)
        return 0

    s3_client.put_json(key=report_s3_key, payload=report)
    LOGGER.info("Uploaded validation report to S3: %s", report_s3_key)

    pushgateway_url = getenv("PUSHGATEWAY_URL")
    if pushgateway_url:
        try:
            _push_metrics(
                pushgateway_url=pushgateway_url,
                dataset_version=args.dataset_version,
                dataset_kind=args.dataset_kind,
                block_metrics=evaluation.block_metrics,
                multilabel_metrics=evaluation.multilabel_metrics,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            # Pushgateway is optional; the report in S3 is the source of truth.
            LOGGER.warning("Failed to push validation metrics to Pushgateway: %s", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
