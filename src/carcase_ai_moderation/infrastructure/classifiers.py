from __future__ import annotations

from dataclasses import dataclass

from carcase_ai_moderation.application.ports import ClassificationResult
from carcase_ai_moderation.domain.moderation import Action, Field


@dataclass(frozen=True, slots=True)
class AlwaysAllowClassifier:
    model: str = "stub"

    def classify(self, *, text: str, action: Action, field: Field) -> ClassificationResult:
        _ = text
        _ = action
        _ = field
        return ClassificationResult(categories=tuple(), model=self.model, reason_short=None)


@dataclass(frozen=True, slots=True)
class StaticClassifier:
    categories: tuple[str, ...]
    model: str = "static"
    reason_short: str | None = "static_result"

    def classify(self, *, text: str, action: Action, field: Field) -> ClassificationResult:
        _ = text
        _ = action
        _ = field
        return ClassificationResult(
            categories=self.categories,
            model=self.model,
            reason_short=self.reason_short,
        )
