from carcase_ai_moderation.domain.moderation import (
    Action,
    Decision,
    Field,
    ModerationInput,
    ModerationResult,
)
from carcase_ai_moderation.infrastructure.event_store import InMemoryModerationEventStore


def test_in_memory_event_store_is_idempotent_by_request_id() -> None:
    store = InMemoryModerationEventStore()
    moderation_input = ModerationInput(
        request_id="r1",
        user_id=1,
        action=Action.CREATE,
        field=Field.SQUAD_NAME,
        text="hello",
    )

    first = ModerationResult(
        decision=Decision.ALLOW,
        categories=(),
        policy_version="v1",
        prompt_version="v1",
        model="stub",
        reason_short=None,
    )
    second = ModerationResult(
        decision=Decision.BLOCK,
        categories=("spam_ads_scam",),
        policy_version="v1",
        prompt_version="v1",
        model="stub",
        reason_short="spam",
    )

    store.save(moderation_input=moderation_input, moderation_result=first)
    store.save(moderation_input=moderation_input, moderation_result=second)

    saved_input, saved_result = store.events_by_request_id["r1"]
    assert saved_input == moderation_input
    assert saved_result == first
