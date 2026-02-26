from __future__ import annotations

from os import getenv
from typing import Any

import httpx
from fastapi import FastAPI
from starlette.responses import JSONResponse

app = FastAPI(title="Alertmanager Telegram Webhook", version="0.1.0")


def _require_env(name: str) -> str:
    value = getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _format_alerts(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    common_labels = payload.get("commonLabels", {})
    alertname = common_labels.get("alertname", "alert")
    severity = common_labels.get("severity", "unknown")

    lines = [f"[{status.upper()}] {alertname} (severity={severity})"]
    for alert in payload.get("alerts", []):
        annotations = alert.get("annotations", {}) if isinstance(alert, dict) else {}
        summary = annotations.get("summary")
        description = annotations.get("description")
        if summary:
            lines.append(f"- {summary}")
        if description:
            lines.append(f"  {description}")

    return "\n".join(lines)


async def _send_telegram_message(*, token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
    response.raise_for_status()


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/alert")
async def alert(payload: dict[str, Any]) -> JSONResponse:
    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    text = _format_alerts(payload)
    await _send_telegram_message(token=token, chat_id=chat_id, text=text)
    return JSONResponse({"status": "sent"})
