from carcase_ai_moderation.application.policy import DEFAULT_POLICY
from carcase_ai_moderation.application.rules import RuleBasedBlocker
from carcase_ai_moderation.application.service import ModerationService
from carcase_ai_moderation.domain.moderation import Action, Decision, Field, ModerationInput
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
