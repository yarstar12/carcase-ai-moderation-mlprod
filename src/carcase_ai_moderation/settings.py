from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from carcase_ai_moderation.application.policy import DEFAULT_POLICY, Policy


@dataclass(frozen=True, slots=True)
class Settings:
    policy: Policy

    @classmethod
    def from_env(cls) -> "Settings":
        policy_version = getenv("POLICY_VERSION", DEFAULT_POLICY.policy_version)
        prompt_version = getenv("PROMPT_VERSION", DEFAULT_POLICY.prompt_version)
        return cls(
            policy=Policy(
                policy_version=policy_version,
                prompt_version=prompt_version,
                hard_block_categories=DEFAULT_POLICY.hard_block_categories,
                review_categories=DEFAULT_POLICY.review_categories,
            )
        )
