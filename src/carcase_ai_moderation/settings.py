from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from carcase_ai_moderation.application.policy import DEFAULT_POLICY, Policy


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    policy: Policy
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str
    openai_timeout_s: float
    database_url: str | None
    event_store_enabled: bool

    @classmethod
    def from_env(cls) -> "Settings":
        policy_version = getenv("POLICY_VERSION") or DEFAULT_POLICY.policy_version
        prompt_version = getenv("PROMPT_VERSION") or DEFAULT_POLICY.prompt_version
        openai_api_key = getenv("OPENAI_API_KEY")
        openai_model = getenv("OPENAI_MODEL", "gpt-4o-mini")
        openai_base_url = getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        openai_timeout_s = float(getenv("OPENAI_TIMEOUT_S", "10.0"))
        database_url = getenv("DATABASE_URL")
        event_store_enabled = _parse_bool(getenv("EVENT_STORE_ENABLED", "0"))
        return cls(
            policy=Policy(
                policy_version=policy_version,
                prompt_version=prompt_version,
                hard_block_categories=DEFAULT_POLICY.hard_block_categories,
                review_categories=DEFAULT_POLICY.review_categories,
            ),
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            openai_base_url=openai_base_url,
            openai_timeout_s=openai_timeout_s,
            database_url=database_url,
            event_store_enabled=event_store_enabled,
        )
