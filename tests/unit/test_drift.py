from carcase_ai_moderation.application.drift import normalize_counts, psi


def test_normalize_counts_empty() -> None:
    assert normalize_counts({}) == {}


def test_normalize_counts_filters_non_positive() -> None:
    assert normalize_counts({"a": 1, "b": 0}) == {"a": 1.0}


def test_psi_is_zero_for_same_distribution() -> None:
    expected = {"a": 0.5, "b": 0.5}
    actual = {"a": 0.5, "b": 0.5}
    assert psi(expected=expected, actual=actual) == 0.0


def test_psi_rejects_non_positive_epsilon() -> None:
    expected = {"a": 1.0}
    actual = {"a": 1.0}
    try:
        psi(expected=expected, actual=actual, epsilon=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")
