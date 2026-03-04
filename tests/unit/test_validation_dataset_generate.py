from carcase_ai_moderation.application.policy import DEFAULT_POLICY
from carcase_ai_moderation.batch.validation_dataset_generate import generate_examples


def test_generate_examples_produces_valid_schema() -> None:
    examples = generate_examples(dataset_version="v1", dataset_kind="smoke", total=50, seed=1)
    assert len(examples) == 50

    ids = {ex["id"] for ex in examples}
    assert len(ids) == 50

    for ex in examples:
        assert ex["dataset_version"] == "v1"
        assert ex["field"] in {"squad_name", "squad_description"}
        assert ex["action"] in {"create", "update"}
        assert isinstance(ex["text"], str) and ex["text"].strip()

        expected_categories = ex["expected_categories"]
        assert isinstance(expected_categories, list)
        assert all(isinstance(c, str) for c in expected_categories)

        expected_decision = ex["expected_decision"]
        assert expected_decision in {"allow", "block", "review"}
        assert expected_decision == DEFAULT_POLICY.decision_for_categories(set(expected_categories))
