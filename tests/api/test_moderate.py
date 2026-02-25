from fastapi.testclient import TestClient

from carcase_ai_moderation.application.policy import DEFAULT_POLICY
from carcase_ai_moderation.application.service import ModerationService
from carcase_ai_moderation.infrastructure.classifiers import StaticClassifier
from service.main import create_app


def test_moderate_returns_allow_for_empty_categories() -> None:
    moderation_service = ModerationService(
        policy=DEFAULT_POLICY,
        classifier=StaticClassifier(categories=tuple()),
    )
    client = TestClient(create_app(moderation_service=moderation_service))

    response = client.post(
        "/moderate",
        json={
            "request_id": "r1",
            "user_id": 1,
            "action": "create",
            "field": "squad_name",
            "text": "normal squad name",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "allow"
    assert payload["categories"] == []


def test_metrics_endpoint_returns_text() -> None:
    client = TestClient(create_app())
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
