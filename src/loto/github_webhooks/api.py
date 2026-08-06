from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from loto.github_webhooks.service import ReceiverService


def create_github_webhook_router(service: ReceiverService) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/github", include_in_schema=False)
    async def github_webhook(request: Request) -> JSONResponse:
        raw_body = await request.body()
        result = service.receive(raw_body=raw_body, raw_headers=dict(request.headers))
        return JSONResponse(
            status_code=result.status_code,
            content=result.model_dump(mode="json", exclude={"status_code"}),
        )

    @router.get("/webhooks/github/health", include_in_schema=False)
    async def github_webhook_health() -> JSONResponse:
        health = service.health()
        return JSONResponse(
            status_code=200 if health["status"] == "ready" else 503,
            content=health,
        )

    return router
