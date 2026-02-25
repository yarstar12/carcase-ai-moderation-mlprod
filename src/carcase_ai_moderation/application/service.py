from __future__ import annotations

from carcase_ai_moderation.application.policy import Policy
from carcase_ai_moderation.application.ports import ClassificationError, TextClassifierPort
from carcase_ai_moderation.application.rules import RuleBasedBlocker
from carcase_ai_moderation.application.text import normalize_text
from carcase_ai_moderation.domain.moderation import Decision, ModerationInput, ModerationResult


class ModerationService:
    def __init__(
        self,
        *,
        policy: Policy,
        classifier: TextClassifierPort,
        rule_blocker: RuleBasedBlocker | None = None,
    ) -> None:
        self._policy = policy
        self._classifier = classifier
        self._rule_blocker = rule_blocker or RuleBasedBlocker()

    def moderate(self, moderation_input: ModerationInput) -> ModerationResult:
        text_norm = normalize_text(moderation_input.text)
        rule_categories = self._rule_blocker.categories_for_text(text_norm)
        if rule_categories:
            decision_str = self._policy.decision_for_categories(rule_categories)
            return ModerationResult(
                decision=Decision(decision_str),
                categories=tuple(sorted(rule_categories)),
                reason_short="rule_based_block",
                policy_version=self._policy.policy_version,
                prompt_version=self._policy.prompt_version,
                model="rules",
            )

        try:
            classification = self._classifier.classify(
                text=moderation_input.text,
                action=moderation_input.action,
                field=moderation_input.field,
            )
        except ClassificationError:
            return ModerationResult(
                decision=Decision.REVIEW,
                categories=("classifier_error",),
                reason_short="classifier_error",
                policy_version=self._policy.policy_version,
                prompt_version=self._policy.prompt_version,
                model="fallback",
            )
        categories = set(classification.categories)
        decision_str = self._policy.decision_for_categories(categories)

        return ModerationResult(
            decision=Decision(decision_str),
            categories=classification.categories,
            reason_short=classification.reason_short,
            policy_version=self._policy.policy_version,
            prompt_version=self._policy.prompt_version,
            model=classification.model,
        )
