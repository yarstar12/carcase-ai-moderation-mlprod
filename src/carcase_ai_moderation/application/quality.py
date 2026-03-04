from __future__ import annotations

from dataclasses import dataclass

from carcase_ai_moderation.domain.moderation import Decision


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    example_id: str
    expected_decision: Decision
    predicted_decision: Decision
    expected_categories: frozenset[str]
    predicted_categories: frozenset[str]


@dataclass(frozen=True, slots=True)
class BlockDecisionMetrics:
    total: int
    review_rate: float
    allow_rate: float
    block_rate: float
    accuracy: float
    precision_block: float
    recall_block_strict: float
    recall_block_safe: float
    f1_block: float
    critical_fn_rate: float


@dataclass(frozen=True, slots=True)
class CategoryMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float


@dataclass(frozen=True, slots=True)
class MultiLabelMetrics:
    micro_precision: float
    micro_recall: float
    micro_f1: float
    per_category: dict[str, CategoryMetrics]


def _safe_div(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _f1(precision: float, recall: float) -> float:
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def compute_block_decision_metrics(records: list[EvaluationRecord]) -> BlockDecisionMetrics:
    total = len(records)
    if total == 0:
        return BlockDecisionMetrics(
            total=0,
            review_rate=0.0,
            allow_rate=0.0,
            block_rate=0.0,
            accuracy=0.0,
            precision_block=0.0,
            recall_block_strict=0.0,
            recall_block_safe=0.0,
            f1_block=0.0,
            critical_fn_rate=0.0,
        )

    correct = 0
    tp_block = 0
    fp_block = 0
    fn_block = 0
    expected_block_total = 0
    expected_block_pred_allow = 0
    expected_block_pred_safe = 0

    predicted_allow_total = 0
    predicted_block_total = 0
    predicted_review_total = 0

    for record in records:
        if record.expected_decision == record.predicted_decision:
            correct += 1

        if record.predicted_decision == Decision.ALLOW:
            predicted_allow_total += 1
        elif record.predicted_decision == Decision.BLOCK:
            predicted_block_total += 1
        else:
            predicted_review_total += 1

        if record.expected_decision == Decision.BLOCK:
            expected_block_total += 1
            if record.predicted_decision == Decision.BLOCK:
                tp_block += 1
            else:
                fn_block += 1

            if record.predicted_decision == Decision.ALLOW:
                expected_block_pred_allow += 1
            else:
                expected_block_pred_safe += 1
        else:
            if record.predicted_decision == Decision.BLOCK:
                fp_block += 1

    precision_block = _safe_div(tp_block, tp_block + fp_block)
    recall_strict = _safe_div(tp_block, expected_block_total)
    recall_safe = _safe_div(expected_block_pred_safe, expected_block_total)
    f1_block = _f1(precision_block, recall_strict)
    critical_fn_rate = _safe_div(expected_block_pred_allow, expected_block_total)

    return BlockDecisionMetrics(
        total=total,
        review_rate=_safe_div(predicted_review_total, total),
        allow_rate=_safe_div(predicted_allow_total, total),
        block_rate=_safe_div(predicted_block_total, total),
        accuracy=_safe_div(correct, total),
        precision_block=precision_block,
        recall_block_strict=recall_strict,
        recall_block_safe=recall_safe,
        f1_block=f1_block,
        critical_fn_rate=critical_fn_rate,
    )


def compute_multilabel_metrics(records: list[EvaluationRecord]) -> MultiLabelMetrics:
    per_category_counts: dict[str, dict[str, int]] = {}

    micro_tp = 0
    micro_fp = 0
    micro_fn = 0

    for record in records:
        expected = record.expected_categories
        predicted = record.predicted_categories

        for category in expected | predicted:
            if category not in per_category_counts:
                per_category_counts[category] = {"tp": 0, "fp": 0, "fn": 0}

        for category in predicted - expected:
            per_category_counts[category]["fp"] += 1
            micro_fp += 1

        for category in expected - predicted:
            per_category_counts[category]["fn"] += 1
            micro_fn += 1

        for category in expected & predicted:
            per_category_counts[category]["tp"] += 1
            micro_tp += 1

    per_category_metrics: dict[str, CategoryMetrics] = {}
    for category, counts in sorted(per_category_counts.items()):
        true_positives = counts["tp"]
        false_positives = counts["fp"]
        false_negatives = counts["fn"]
        precision = _safe_div(true_positives, true_positives + false_positives)
        recall = _safe_div(true_positives, true_positives + false_negatives)
        per_category_metrics[category] = CategoryMetrics(
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            precision=precision,
            recall=recall,
            f1_score=_f1(precision, recall),
        )

    micro_precision = _safe_div(micro_tp, micro_tp + micro_fp)
    micro_recall = _safe_div(micro_tp, micro_tp + micro_fn)
    return MultiLabelMetrics(
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=_f1(micro_precision, micro_recall),
        per_category=per_category_metrics,
    )


def decision_confusion_matrix(records: list[EvaluationRecord]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for record in records:
        expected = record.expected_decision.value
        predicted = record.predicted_decision.value
        if expected not in matrix:
            matrix[expected] = {}
        matrix[expected][predicted] = matrix[expected].get(predicted, 0) + 1
    return matrix
