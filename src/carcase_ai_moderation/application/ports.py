from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from carcase_ai_moderation.domain.moderation import Action, Field


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    categories: tuple[str, ...]
    model: str
    reason_short: str | None = None


class ClassificationError(RuntimeError):
    pass


class TextClassifierPort(Protocol):
    def classify(self, *, text: str, action: Action, field: Field) -> ClassificationResult: ...
