from __future__ import annotations

from dataclasses import dataclass, field

from carcase_ai_moderation.domain.moderation import ModerationInput, ModerationResult


@dataclass(slots=True)
class InMemoryModerationEventStore:
    events_by_request_id: dict[str, tuple[ModerationInput, ModerationResult]] = field(
        default_factory=dict
    )

    def save(
        self, *, moderation_input: ModerationInput, moderation_result: ModerationResult
    ) -> None:
        self.events_by_request_id.setdefault(
            moderation_input.request_id,
            (moderation_input, moderation_result),
        )
