from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, cast

from carcase_ai_moderation.application.ports import EventStoreError
from carcase_ai_moderation.application.text import normalize_text
from carcase_ai_moderation.domain.moderation import ModerationInput, ModerationResult


def _import_psycopg() -> Any:
    try:
        return importlib.import_module("psycopg")
    except ModuleNotFoundError as exc:
        raise EventStoreError("psycopg is required for Postgres event store") from exc


@dataclass(frozen=True, slots=True)
class PostgresModerationEventStore:
    database_url: str

    def save(
        self, *, moderation_input: ModerationInput, moderation_result: ModerationResult
    ) -> None:
        psycopg = _import_psycopg()
        psycopg_error = cast(type[BaseException], psycopg.Error)

        text_norm = normalize_text(moderation_input.text)
        categories_json = json.dumps(list(moderation_result.categories))

        sql = """
            insert into moderation_events (
                request_id,
                user_id,
                action,
                field,
                text_raw,
                text_norm,
                decision,
                categories,
                reason_short,
                policy_version,
                prompt_version,
                model
            )
            values (
                %(request_id)s,
                %(user_id)s,
                %(action)s,
                %(field)s,
                %(text_raw)s,
                %(text_norm)s,
                %(decision)s,
                %(categories)s::jsonb,
                %(reason_short)s,
                %(policy_version)s,
                %(prompt_version)s,
                %(model)s
            )
            on conflict (request_id) do nothing
        """
        params = {
            "request_id": moderation_input.request_id,
            "user_id": moderation_input.user_id,
            "action": moderation_input.action.value,
            "field": moderation_input.field.value,
            "text_raw": moderation_input.text,
            "text_norm": text_norm,
            "decision": moderation_result.decision.value,
            "categories": categories_json,
            "reason_short": moderation_result.reason_short,
            "policy_version": moderation_result.policy_version,
            "prompt_version": moderation_result.prompt_version,
            "model": moderation_result.model,
        }

        try:
            with psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
        except psycopg_error as exc:
            raise EventStoreError("Postgres write failed") from exc
