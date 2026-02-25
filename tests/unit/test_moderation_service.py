from carcase_ai_moderation.application.policy import DEFAULT_POLICY
from carcase_ai_moderation.application.ports import (
    ClassificationError,
    ClassificationResult,
    EventStoreError,
)
from carcase_ai_moderation.application.rules import RuleBasedBlocker
from carcase_ai_moderation.application.service import ModerationService
from carcase_ai_moderation.domain.moderation import (
    Action,
    Decision,
    Field,
    ModerationInput,
    ModerationResult,
)
from carcase_ai_moderation.infrastructure.classifiers import StaticClassifier


def test_rule_blocks_url_as_spam() -> None:
    service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=StaticClassifier(categories=tuple()),
        rule_blocker=RuleBasedBlocker(),
    )

    result = service.moderate(
        ModerationInput(
            request_id="r1",
            user_id=1,
            action=Action.CREATE,
            field=Field.SQUAD_DESCRIPTION,
            text="join https://example.com",
        )
    )

    assert result.decision == Decision.BLOCK
    assert "spam_ads_scam" in result.categories


def test_llm_categories_map_to_block_for_hard_block_category() -> None:
    service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=StaticClassifier(categories=("hate_extremism_terror",)),
        rule_blocker=RuleBasedBlocker(),
    )

    result = service.moderate(
        ModerationInput(
            request_id="r2",
            user_id=1,
            action=Action.CREATE,
            field=Field.SQUAD_NAME,
            text="some text",
        )
    )

    assert result.decision == Decision.BLOCK


def test_rule_flags_long_number_as_pii_and_sends_to_review() -> None:
    service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=StaticClassifier(categories=tuple()),
        rule_blocker=RuleBasedBlocker(),
    )

    result = service.moderate(
        ModerationInput(
            request_id="r3",
            user_id=1,
            action=Action.UPDATE,
            field=Field.SQUAD_DESCRIPTION,
            text="my phone is 79991234567",
        )
    )

    assert result.decision == Decision.REVIEW
    assert "pii_doxxing" in result.categories


def test_classifier_error_falls_back_to_review() -> None:
    class FailingClassifier:
        def classify(self, *, text: str, action: Action, field: Field) -> ClassificationResult:
            _ = text
            _ = action
            _ = field
            raise ClassificationError("boom")

    service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=FailingClassifier(),
        rule_blocker=RuleBasedBlocker(),
    )

    result = service.moderate(
        ModerationInput(
            request_id="r4",
            user_id=1,
            action=Action.CREATE,
            field=Field.SQUAD_NAME,
            text="some text",
        )
    )

    assert result.decision == Decision.REVIEW
    assert "classifier_error" in result.categories


def test_moderation_service_persists_event_when_store_provided() -> None:
    class RecordingStore:
        def __init__(self) -> None:
            self.saved: list[tuple[ModerationInput, ModerationResult]] = []

        def save(
            self, *, moderation_input: ModerationInput, moderation_result: ModerationResult
        ) -> None:
            self.saved.append((moderation_input, moderation_result))

    store = RecordingStore()
    service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=StaticClassifier(categories=tuple()),
        rule_blocker=RuleBasedBlocker(),
        event_store=store,
    )

    moderation_input = ModerationInput(
        request_id="r5",
        user_id=1,
        action=Action.CREATE,
        field=Field.SQUAD_NAME,
        text="some text",
    )
    result = service.moderate(moderation_input)

    assert store.saved == [(moderation_input, result)]


def test_event_store_error_does_not_break_moderation() -> None:
    class FailingStore:
        def save(
            self, *, moderation_input: ModerationInput, moderation_result: ModerationResult
        ) -> None:
            _ = moderation_input
            _ = moderation_result
            raise EventStoreError("db down")

    service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=StaticClassifier(categories=("hate_extremism_terror",)),
        rule_blocker=RuleBasedBlocker(),
        event_store=FailingStore(),
    )

    result = service.moderate(
        ModerationInput(
            request_id="r6",
            user_id=1,
            action=Action.CREATE,
            field=Field.SQUAD_NAME,
            text="some text",
        )
    )

    assert result.decision == Decision.BLOCK
