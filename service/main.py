from __future__ import annotations

import time

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from carcase_ai_moderation.application.ports import TextClassifierPort
from carcase_ai_moderation.application.service import ModerationService
from carcase_ai_moderation.domain.moderation import Action, Decision
from carcase_ai_moderation.domain.moderation import Field as ModerationField
from carcase_ai_moderation.domain.moderation import ModerationInput
from carcase_ai_moderation.infrastructure.classifiers import AlwaysAllowClassifier
from carcase_ai_moderation.infrastructure.openai_classifier import OpenAIChatCompletionsClassifier
from carcase_ai_moderation.infrastructure.postgres_event_store import PostgresModerationEventStore
from carcase_ai_moderation.settings import Settings

REQUESTS_TOTAL = Counter(
    "moderation_requests_total",
    "Total moderation requests",
    labelnames=("decision", "field", "action"),
)
REQUEST_LATENCY_SECONDS = Histogram(
    "moderation_request_latency_seconds",
    "Latency of moderation requests in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)


class ModerateRequest(BaseModel):
    request_id: str = Field(min_length=1)
    user_id: int = Field(ge=1)
    action: Action
    field: ModerationField
    text: str = Field(min_length=1)


class ModerateResponse(BaseModel):
    decision: Decision
    categories: list[str]
    reason_short: str | None = None
    policy_version: str
    prompt_version: str
    model: str


def create_app(*, moderation_service: ModerationService | None = None) -> FastAPI:
    settings = Settings.from_env()
    if moderation_service is None:
        classifier: TextClassifierPort
        if settings.openai_api_key:
            classifier = OpenAIChatCompletionsClassifier(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                base_url=settings.openai_base_url,
                timeout_s=settings.openai_timeout_s,
            )
        else:
            classifier = AlwaysAllowClassifier()

        event_store = None
        if settings.event_store_enabled and settings.database_url:
            event_store = PostgresModerationEventStore(settings.database_url)

        service = ModerationService(
            policy=settings.policy,
            classifier=classifier,
            event_store=event_store,
        )
    else:
        service = moderation_service

    fastapi_app = FastAPI(title="CARCASE Moderation Service", version="0.1.0")

    @fastapi_app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @fastapi_app.post("/moderate", response_model=ModerateResponse)
    def moderate(request: ModerateRequest) -> ModerateResponse:
        started = time.perf_counter()
        result = service.moderate(
            ModerationInput(
                request_id=request.request_id,
                user_id=request.user_id,
                action=request.action,
                field=request.field,
                text=request.text,
            )
        )
        elapsed = time.perf_counter() - started

        REQUEST_LATENCY_SECONDS.observe(elapsed)
        REQUESTS_TOTAL.labels(
            decision=result.decision.value,
            field=request.field.value,
            action=request.action.value,
        ).inc()

        return ModerateResponse(
            decision=result.decision,
            categories=list(result.categories),
            reason_short=result.reason_short,
            policy_version=result.policy_version,
            prompt_version=result.prompt_version,
            model=result.model,
        )

    @fastapi_app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return fastapi_app


app = create_app()
