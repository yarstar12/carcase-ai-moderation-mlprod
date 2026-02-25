from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Policy:
    policy_version: str
    prompt_version: str
    hard_block_categories: frozenset[str]
    review_categories: frozenset[str]

    def decision_for_categories(self, categories: set[str]) -> str:
        if categories & set(self.hard_block_categories):
            return "block"
        if categories & set(self.review_categories):
            return "review"
        if categories:
            return "review"
        return "allow"


DEFAULT_POLICY = Policy(
    policy_version="v1",
    prompt_version="v1",
    hard_block_categories=frozenset(
        {
            "hate_extremism_terror",
            "sexual_minors",
            "self_harm_instructions",
            "violence_threats",
            "spam_ads_scam",
            "profanity_insult_harassment",
        }
    ),
    review_categories=frozenset({"pii_doxxing"}),
)
