from __future__ import annotations

import math
from collections.abc import Mapping


def normalize_counts(counts: Mapping[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in counts.items() if value > 0}


def psi(
    *, expected: Mapping[str, float], actual: Mapping[str, float], epsilon: float = 1e-6
) -> float:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")

    keys = set(expected) | set(actual)
    index = 0.0
    for key in keys:
        expected_p = max(expected.get(key, 0.0), epsilon)
        actual_p = max(actual.get(key, 0.0), epsilon)
        index += (actual_p - expected_p) * math.log(actual_p / expected_p)
    return index
