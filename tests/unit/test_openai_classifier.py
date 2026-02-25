import json

import httpx
import pytest

from carcase_ai_moderation.application.ports import ClassificationError
from carcase_ai_moderation.domain.moderation import Action, Field
from carcase_ai_moderation.infrastructure.openai_classifier import OpenAIChatCompletionsClassifier


def test_openai_classifier_parses_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["temperature"] == 0
        assert payload["model"] == "gpt-test"

        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "choices": [
                    {
                        "message": {
                            "content": '{"categories":["spam_ads_scam"],"reason_short":"ads"}',
                        }
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    classifier = OpenAIChatCompletionsClassifier(
        api_key="k",
        model="gpt-test",
        base_url="https://api.openai.com/v1",
        http_client=client,
    )

    result = classifier.classify(
        text="join https://example.com", action=Action.CREATE, field=Field.SQUAD_NAME
    )
    assert result.categories == ("spam_ads_scam",)
    assert result.model == "gpt-test"

    client.close()


def test_openai_classifier_ignores_unknown_categories() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"categories":["unknown","pii_doxxing"],' '"reason_short":"pii"}'
                            ),
                        }
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    classifier = OpenAIChatCompletionsClassifier(api_key="k", model="gpt-test", http_client=client)

    result = classifier.classify(
        text="79991234567", action=Action.UPDATE, field=Field.SQUAD_DESCRIPTION
    )
    assert result.categories == ("pii_doxxing",)

    client.close()


def test_openai_classifier_unknown_only_triggers_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "choices": [
                    {
                        "message": {
                            "content": '{"categories":["unknown"],"reason_short":"unknown"}',
                        }
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    classifier = OpenAIChatCompletionsClassifier(api_key="k", model="gpt-test", http_client=client)

    with pytest.raises(ClassificationError):
        classifier.classify(text="x", action=Action.CREATE, field=Field.SQUAD_NAME)

    client.close()
