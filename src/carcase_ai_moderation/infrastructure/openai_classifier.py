from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

import httpx

from carcase_ai_moderation.application.ports import ClassificationError, ClassificationResult
from carcase_ai_moderation.domain.moderation import Action, Field

ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "profanity_insult_harassment",
        "hate_extremism_terror",
        "sexual",
        "sexual_minors",
        "self_harm_instructions",
        "violence_threats",
        "spam_ads_scam",
        "pii_doxxing",
    }
)

SYSTEM_PROMPT = (
    "You are a strict content moderation classifier for a gaming product. "
    "Classify user-provided text for policy violations. "
    "Return ONLY a JSON object."
)


def _build_user_prompt(*, text: str, action: Action, field: Field) -> str:
    allowed_lines = "\n".join(f"- {c}" for c in sorted(ALLOWED_CATEGORIES))
    return (
        "Task: classify the text for policy violations.\n"
        f"Field: {field.value}\n"
        f"Action: {action.value}\n"
        f"Text: {text}\n\n"
        "Allowed categories:\n"
        f"{allowed_lines}\n\n"
        'Return JSON with keys: {"categories": [...], "reason_short": "..."}.\n'
        "If there are no violations, return an empty categories list."
    )


def _parse_openai_response(data: object, *, default_model: str) -> ClassificationResult:
    if not isinstance(data, dict):
        raise ClassificationError("Unexpected OpenAI response shape")

    model_name = data.get("model")
    if not isinstance(model_name, str):
        model_name = default_model

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ClassificationError("Unexpected OpenAI response shape") from exc

    if not isinstance(content, str):
        raise ClassificationError("OpenAI content must be a string")

    payload = _extract_json_object(content)
    raw_categories = payload.get("categories", [])
    reason_short = payload.get("reason_short")

    if not isinstance(raw_categories, list) or not all(isinstance(x, str) for x in raw_categories):
        raise ClassificationError("categories must be a list of strings")

    if reason_short is not None and not isinstance(reason_short, str):
        raise ClassificationError("reason_short must be a string")

    allowed = {c for c in raw_categories if c in ALLOWED_CATEGORIES}
    unknown = {c for c in raw_categories if c not in ALLOWED_CATEGORIES}
    if unknown and not allowed:
        raise ClassificationError("Unknown moderation categories returned by the classifier")

    categories = tuple(sorted(allowed))
    return ClassificationResult(categories=categories, model=model_name, reason_short=reason_short)


def _extract_json_object(text: str) -> dict[str, object]:
    content = text.strip()
    if content.startswith("```"):
        lines = [line for line in content.splitlines() if not line.strip().startswith("```")]
        content = "\n".join(lines).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ClassificationError("LLM output does not contain a JSON object")

    try:
        payload = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ClassificationError("Failed to parse LLM JSON output") from exc

    if not isinstance(payload, dict):
        raise ClassificationError("LLM output JSON must be an object")

    return cast(dict[str, object], payload)


@dataclass(frozen=True, slots=True)
class OpenAIChatCompletionsClassifier:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_s: float = 10.0
    http_client: httpx.Client | None = None

    def _post_chat_completions(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> object:
        if self.http_client is not None:
            return self._post_json(self.http_client, url=url, headers=headers, body=body)

        with httpx.Client(timeout=self.timeout_s) as client:
            return self._post_json(client, url=url, headers=headers, body=body)

    @staticmethod
    def _post_json(
        client: httpx.Client, *, url: str, headers: dict[str, str], body: dict[str, object]
    ) -> object:
        try:
            response = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ClassificationError("OpenAI request failed") from exc

        if response.status_code != 200:
            raise ClassificationError(f"OpenAI returned status {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise ClassificationError("Failed to decode OpenAI JSON response") from exc

    def classify(self, *, text: str, action: Action, field: Field) -> ClassificationResult:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_user_prompt(text=text, action=action, field=field),
                },
            ],
        }

        data = self._post_chat_completions(url=url, headers=headers, body=body)
        return _parse_openai_response(data, default_model=self.model)
