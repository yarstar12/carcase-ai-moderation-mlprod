from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from carcase_ai_moderation.application.policy import DEFAULT_POLICY
from carcase_ai_moderation.application.quality import (
    BlockDecisionMetrics,
    CategoryMetrics,
    MultiLabelMetrics,
)
from carcase_ai_moderation.batch import validation_evaluate
from carcase_ai_moderation.batch.validation_evaluate import (
    build_dataset_s3_key,
    build_report_s3_key,
)
from carcase_ai_moderation.domain.moderation import Action, Decision, Field
from carcase_ai_moderation.settings import Settings


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


def test_parse_iso_date_raises_on_invalid_format() -> None:
    with pytest.raises(validation_evaluate.BatchError, match="YYYY-MM-DD"):
        validation_evaluate._parse_iso_date("2026/02/26")


def test_normalize_prefix_trims_slashes() -> None:
    assert validation_evaluate._normalize_prefix(" /datasets/validation/ ") == "datasets/validation"


def test_normalize_prefix_raises_on_empty() -> None:
    with pytest.raises(validation_evaluate.BatchError, match="prefix must not be empty"):
        validation_evaluate._normalize_prefix(" / ")


def test_parse_example_and_redacted_detection() -> None:
    example = validation_evaluate._parse_example(
        {
            "id": "e1",
            "dataset_version": "v1",
            "field": "squad_name",
            "action": "create",
            "text": "hello",
            "expected_categories": [],
            "expected_decision": "allow",
            "source": "synthetic",
            "notes": None,
        }
    )

    assert example.example_id == "e1"
    assert example.field == Field.SQUAD_NAME
    assert example.action == Action.CREATE
    assert example.expected_decision == Decision.ALLOW
    assert validation_evaluate._looks_redacted(example) is False

    redacted = validation_evaluate.ValidationExample(
        example_id="e2",
        dataset_version="v1",
        field=Field.SQUAD_DESCRIPTION,
        action=Action.UPDATE,
        text="Hello [REDACTED_NAME]",
        expected_categories=frozenset(),
        expected_decision=Decision.ALLOW,
        source="synthetic",
        notes="placeholder example",
    )
    assert validation_evaluate._looks_redacted(redacted) is True


def test_load_jsonl_raises_on_invalid_json_line() -> None:
    text = (
        '{"id":"e1","dataset_version":"v1","field":"squad_name","action":"create",'
        '"text":"ok","expected_categories":[],"expected_decision":"allow","source":"synthetic"}\n'
        "not-json\n"
    )
    with pytest.raises(validation_evaluate.BatchError, match="Invalid JSON at line 2"):
        validation_evaluate._load_jsonl(text)


def test_select_examples_skips_redacted_and_honors_max_examples() -> None:
    examples = [
        validation_evaluate.ValidationExample(
            example_id="e1",
            dataset_version="v1",
            field=Field.SQUAD_NAME,
            action=Action.CREATE,
            text="Hello [REDACTED_X]",
            expected_categories=frozenset(),
            expected_decision=Decision.ALLOW,
            source="synthetic",
            notes=None,
        ),
        validation_evaluate.ValidationExample(
            example_id="e2",
            dataset_version="v1",
            field=Field.SQUAD_NAME,
            action=Action.CREATE,
            text="normal",
            expected_categories=frozenset(),
            expected_decision=Decision.ALLOW,
            source="synthetic",
            notes=None,
        ),
        validation_evaluate.ValidationExample(
            example_id="e3",
            dataset_version="v1",
            field=Field.SQUAD_NAME,
            action=Action.CREATE,
            text="another",
            expected_categories=frozenset(),
            expected_decision=Decision.ALLOW,
            source="synthetic",
            notes=None,
        ),
    ]

    selected, skipped = validation_evaluate._select_examples(
        examples=examples,
        include_redacted=False,
        max_examples=1,
    )
    assert [e.example_id for e in selected] == ["e2"]
    assert skipped == 1


def test_load_dataset_from_local_path(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                json_line
                for json_line in [
                    (
                        '{"id":"e1","dataset_version":"v1","field":"squad_name",'
                        '"action":"create","text":"ok","expected_categories":[],'
                        '"expected_decision":"allow","source":"synthetic"}'
                    )
                ]
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    examples, source = validation_evaluate._load_dataset(
        dataset_path=str(dataset_path),
        datasets_prefix="datasets/validation",
        dataset_version="v1",
        dataset_kind="smoke",
    )
    assert len(examples) == 1
    assert source == {"type": "local", "path": str(dataset_path)}


def test_load_dataset_from_s3_when_path_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    jsonl = (
        '{"id":"e1","dataset_version":"v1","field":"squad_name","action":"create",'
        '"text":"ok","expected_categories":[],"expected_decision":"allow","source":"synthetic"}\n'
    )

    class FakeConfig:
        bucket: str = "bucket"

    class FakeS3:
        def __init__(self) -> None:
            self.config = FakeConfig()

        def get_text(self, *, key: str) -> str:
            assert key == "datasets/validation/v1.smoke.jsonl"
            return jsonl

    def fake_s3_client_from_env() -> FakeS3:
        return FakeS3()

    monkeypatch.setattr(validation_evaluate, "_s3_client_from_env", fake_s3_client_from_env)

    examples, source = validation_evaluate._load_dataset(
        dataset_path=None,
        datasets_prefix="datasets/validation",
        dataset_version="v1",
        dataset_kind="smoke",
    )
    assert len(examples) == 1
    assert source == {
        "type": "s3",
        "key": "datasets/validation/v1.smoke.jsonl",
        "bucket": "bucket",
    }


def test_run_evaluation_uses_stub_classifier_when_openai_key_missing() -> None:
    settings = Settings(
        policy=DEFAULT_POLICY,
        openai_api_key=None,
        openai_model="gpt-test",
        openai_base_url="https://api.openai.com/v1",
        openai_timeout_s=1.0,
        database_url=None,
        event_store_enabled=False,
    )
    examples = [
        validation_evaluate.ValidationExample(
            example_id="e1",
            dataset_version="v1",
            field=Field.SQUAD_NAME,
            action=Action.CREATE,
            text="normal name",
            expected_categories=frozenset(),
            expected_decision=Decision.ALLOW,
            source="synthetic",
            notes=None,
        )
    ]

    result = validation_evaluate._run_evaluation(examples=examples, settings=settings)
    assert result.block_metrics.total == 1
    assert result.block_metrics.accuracy == 1.0
    assert result.confusion == {"allow": {"allow": 1}}
    assert result.multilabel_metrics.per_category == {}


def test_build_report_sets_openai_fields_to_none_when_key_missing() -> None:
    settings = Settings(
        policy=DEFAULT_POLICY,
        openai_api_key=None,
        openai_model="gpt-test",
        openai_base_url="https://api.openai.com/v1",
        openai_timeout_s=1.0,
        database_url=None,
        event_store_enabled=False,
    )
    ctx = validation_evaluate.EvaluationContext(
        run_date=date(2026, 2, 26),
        started_at=datetime(2026, 2, 26, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 2, 26, 10, 0, 1, tzinfo=UTC),
        elapsed_s=1.0,
        dataset_version="v1",
        dataset_kind="smoke",
        examples_total=10,
        examples_evaluated=5,
        examples_skipped_redacted=2,
        dataset_source={"type": "local", "path": "x"},
    )
    block_metrics = BlockDecisionMetrics(
        total=5,
        review_rate=0.0,
        allow_rate=1.0,
        block_rate=0.0,
        accuracy=1.0,
        precision_block=0.0,
        recall_block_strict=0.0,
        recall_block_safe=0.0,
        f1_block=0.0,
        critical_fn_rate=0.0,
    )
    multilabel_metrics = MultiLabelMetrics(
        micro_precision=0.0,
        micro_recall=0.0,
        micro_f1=0.0,
        per_category={"spam_ads_scam": CategoryMetrics(1, 0, 0, 1.0, 1.0, 1.0)},
    )

    report = validation_evaluate._build_report(
        ctx=ctx,
        settings=settings,
        block_metrics=block_metrics,
        multilabel_metrics=multilabel_metrics,
        confusion={"allow": {"allow": 5}},
    )

    versions = report["versions"]
    assert isinstance(versions, dict)
    assert versions["openai_model"] is None
    assert versions["openai_base_url"] is None


def test_main_skips_upload_when_report_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        (
            '{"id":"e1","dataset_version":"v1","field":"squad_name","action":"create",'
            '"text":"ok","expected_categories":[],"expected_decision":"allow",'
            '"source":"synthetic"}\n'
        ),
        encoding="utf-8",
    )

    class FakeS3:
        def __init__(self) -> None:
            self.put_calls: list[tuple[str, dict[str, object]]] = []
            self.exists_calls: list[str] = []

        def object_exists(self, *, key: str) -> bool:
            self.exists_calls.append(key)
            return True

        def put_json(self, *, key: str, payload: dict[str, object]) -> None:
            self.put_calls.append((key, payload))

    fake_s3 = FakeS3()
    monkeypatch.setattr(validation_evaluate, "_s3_client_from_env", lambda: fake_s3)
    monkeypatch.delenv("PUSHGATEWAY_URL", raising=False)

    code = validation_evaluate.main(
        [
            "--run-date",
            "2026-02-26",
            "--dataset-path",
            str(dataset_path),
            "--dataset-version",
            "v1",
            "--dataset-kind",
            "smoke",
        ]
    )
    assert code == 0
    assert fake_s3.exists_calls == ["reports/validation/v1/smoke/2026-02-26.json"]
    assert fake_s3.put_calls == []


def test_main_pushgateway_failure_does_not_fail_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        (
            '{"id":"e1","dataset_version":"v1","field":"squad_name","action":"create",'
            '"text":"ok","expected_categories":[],"expected_decision":"allow",'
            '"source":"synthetic"}\n'
        ),
        encoding="utf-8",
    )

    class FakeS3:
        def __init__(self) -> None:
            self.put_calls: list[tuple[str, dict[str, object]]] = []

        def object_exists(self, *, key: str) -> bool:
            _ = key
            return False

        def put_json(self, *, key: str, payload: dict[str, object]) -> None:
            self.put_calls.append((key, payload))

    def fake_push_metrics(
        *,
        pushgateway_url: str,
        dataset_version: str,
        dataset_kind: str,
        block_metrics: BlockDecisionMetrics,
        multilabel_metrics: MultiLabelMetrics,
    ) -> None:
        _ = pushgateway_url
        _ = dataset_version
        _ = dataset_kind
        _ = block_metrics
        _ = multilabel_metrics
        raise ValueError("pushgateway down")

    fake_s3 = FakeS3()
    monkeypatch.setattr(validation_evaluate, "_s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(validation_evaluate, "_push_metrics", fake_push_metrics)
    monkeypatch.setenv("PUSHGATEWAY_URL", "http://pushgateway:9091")

    code = validation_evaluate.main(
        [
            "--run-date",
            "2026-02-26",
            "--dataset-path",
            str(dataset_path),
            "--dataset-version",
            "v1",
            "--dataset-kind",
            "smoke",
            "--overwrite",
        ]
    )
    assert code == 0
    assert len(fake_s3.put_calls) == 1
