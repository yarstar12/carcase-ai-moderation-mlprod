import pytest

from carcase_ai_moderation.application.quality import (
    EvaluationRecord,
    compute_block_decision_metrics,
    compute_multilabel_metrics,
    decision_confusion_matrix,
)
from carcase_ai_moderation.domain.moderation import Decision


def test_block_metrics_and_confusion_matrix() -> None:
    records = [
        EvaluationRecord(
            example_id="e1",
            expected_decision=Decision.BLOCK,
            predicted_decision=Decision.BLOCK,
            expected_categories=frozenset({"spam_ads_scam"}),
            predicted_categories=frozenset({"spam_ads_scam"}),
        ),
        EvaluationRecord(
            example_id="e2",
            expected_decision=Decision.ALLOW,
            predicted_decision=Decision.BLOCK,
            expected_categories=frozenset(),
            predicted_categories=frozenset({"spam_ads_scam"}),
        ),
        EvaluationRecord(
            example_id="e3",
            expected_decision=Decision.BLOCK,
            predicted_decision=Decision.REVIEW,
            expected_categories=frozenset({"violence_threats"}),
            predicted_categories=frozenset(),
        ),
    ]

    metrics = compute_block_decision_metrics(records)
    assert metrics.total == 3
    assert metrics.accuracy == pytest.approx(1 / 3)
    assert metrics.review_rate == pytest.approx(1 / 3)
    assert metrics.precision_block == pytest.approx(0.5)
    assert metrics.recall_block_strict == pytest.approx(0.5)
    assert metrics.recall_block_safe == pytest.approx(1.0)
    assert metrics.critical_fn_rate == pytest.approx(0.0)

    confusion = decision_confusion_matrix(records)
    assert confusion["block"]["block"] == 1
    assert confusion["allow"]["block"] == 1
    assert confusion["block"]["review"] == 1


def test_multilabel_micro_metrics() -> None:
    records = [
        EvaluationRecord(
            example_id="e1",
            expected_decision=Decision.BLOCK,
            predicted_decision=Decision.BLOCK,
            expected_categories=frozenset({"spam_ads_scam"}),
            predicted_categories=frozenset({"spam_ads_scam"}),
        ),
        EvaluationRecord(
            example_id="e2",
            expected_decision=Decision.ALLOW,
            predicted_decision=Decision.BLOCK,
            expected_categories=frozenset(),
            predicted_categories=frozenset({"spam_ads_scam"}),
        ),
        EvaluationRecord(
            example_id="e3",
            expected_decision=Decision.BLOCK,
            predicted_decision=Decision.REVIEW,
            expected_categories=frozenset({"violence_threats"}),
            predicted_categories=frozenset(),
        ),
    ]

    metrics = compute_multilabel_metrics(records)
    assert metrics.micro_precision == pytest.approx(0.5)
    assert metrics.micro_recall == pytest.approx(0.5)
    assert metrics.micro_f1 == pytest.approx(0.5)

    spam = metrics.per_category["spam_ads_scam"]
    assert spam.true_positives == 1
    assert spam.false_positives == 1
    assert spam.false_negatives == 0
    assert spam.precision == pytest.approx(0.5)
    assert spam.recall == pytest.approx(1.0)

    threats = metrics.per_category["violence_threats"]
    assert threats.true_positives == 0
    assert threats.false_positives == 0
    assert threats.false_negatives == 1
