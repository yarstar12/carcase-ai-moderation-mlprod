from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    CREATE = "create"
    UPDATE = "update"


class Field(StrEnum):
    SQUAD_NAME = "squad_name"
    SQUAD_DESCRIPTION = "squad_description"


class Decision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ModerationInput:
    request_id: str
    user_id: int
    action: Action
    field: Field
    text: str


@dataclass(frozen=True, slots=True)
class ModerationResult:
    decision: Decision
    categories: tuple[str, ...]
    policy_version: str
    prompt_version: str
    model: str
    reason_short: str | None = None
