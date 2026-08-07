from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from loto.github_webhooks.contracts import (
    EventType,
    GitHubWebhookHeaders,
    ReceiverPolicy,
    ReceiverResult,
    StoreOutcome,
)
from loto.github_webhooks.metrics import WebhookMetrics
from loto.github_webhooks.normalization import (
    WebhookNormalizationError,
    normalize_delivery,
)
from loto.github_webhooks.security import (
    DuplicateJsonKeyError,
    SecretRing,
    WebhookSecurityError,
    loads_json_object,
    payload_sha256,
    verify_signature,
)
from loto.github_webhooks.store import WebhookStore


class ReceiverService:
    def __init__(
        self,
        *,
        policy: ReceiverPolicy,
        secrets: SecretRing,
        store: WebhookStore,
        metrics: WebhookMetrics | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.policy = policy
        self.secrets = secrets
        self.store = store
        self.metrics = metrics
        self.logger = logger or logging.getLogger("loto.github_webhooks")

    @staticmethod
    def _headers(raw_headers: Mapping[str, str]) -> dict[str, str]:
        return {key.lower(): value for key, value in raw_headers.items()}

    @staticmethod
    def _content_type(value: str | None) -> str:
        if value is None:
            raise WebhookSecurityError("CONTENT_TYPE_MISSING")
        media_type = value.split(";", maxsplit=1)[0].strip().lower()
        if media_type != "application/json":
            raise WebhookSecurityError("CONTENT_TYPE_UNSUPPORTED")
        return value

    def _parse_headers(self, raw_headers: Mapping[str, str]) -> GitHubWebhookHeaders:
        headers = self._headers(raw_headers)
        event_value = headers.get("x-github-event")
        if event_value is None:
            raise WebhookSecurityError("EVENT_HEADER_MISSING")
        try:
            event_type = EventType(event_value)
        except ValueError as exc:
            raise WebhookSecurityError("EVENT_NOT_ALLOWED") from exc

        delivery_id = headers.get("x-github-delivery")
        if delivery_id is None:
            raise WebhookSecurityError("DELIVERY_ID_MISSING")
        signature = headers.get("x-hub-signature-256")
        if signature is None:
            raise WebhookSecurityError("SIGNATURE_MISSING")

        hook_value = headers.get("x-github-hook-id")
        try:
            hook_id = None if hook_value is None else int(hook_value)
            return GitHubWebhookHeaders(
                event_type=event_type,
                delivery_id=delivery_id,
                signature_256=signature,
                content_type=self._content_type(headers.get("content-type")),
                hook_id=hook_id,
                user_agent=headers.get("user-agent"),
            )
        except (ValidationError, ValueError) as exc:
            if isinstance(exc, WebhookSecurityError):
                raise
            raise WebhookSecurityError("HEADERS_INVALID") from exc

    def _observe(
        self,
        *,
        event: str,
        result: str,
        duration: float,
        signature_failure: bool = False,
        duplicate_result: str | None = None,
    ) -> None:
        if self.metrics is None:
            return
        self.metrics.requests_total.labels(event=event, result=result).inc()
        self.metrics.ack_seconds.labels(event=event, result=result).observe(duration)
        if signature_failure:
            self.metrics.signature_failures_total.inc()
        if duplicate_result is not None:
            self.metrics.duplicates_total.labels(result=duplicate_result).inc()
        self.metrics.queue_depth.set(self.store.queue_depth())

    def _result(
        self,
        *,
        start: float,
        event: str,
        status_code: int,
        result: str,
        trace_id: str,
        delivery_id: str | None = None,
        processing_status: str | None = None,
        error_code: str | None = None,
        signature_failure: bool = False,
        duplicate_result: str | None = None,
    ) -> ReceiverResult:
        duration = time.perf_counter() - start
        self._observe(
            event=event,
            result=result,
            duration=duration,
            signature_failure=signature_failure,
            duplicate_result=duplicate_result,
        )
        self.logger.info(
            "github_webhook_receive",
            extra={
                "webhook_event": event,
                "webhook_result": result,
                "webhook_delivery_id": delivery_id,
                "webhook_trace_id": trace_id,
                "webhook_status": processing_status,
                "webhook_error_code": error_code,
                "webhook_ack_seconds": duration,
            },
        )
        return ReceiverResult(
            status_code=status_code,
            result=result,
            delivery_id=delivery_id,
            trace_id=trace_id,
            processing_status=processing_status,
            error_code=error_code,
        )

    def receive(
        self,
        *,
        raw_body: bytes,
        raw_headers: Mapping[str, str],
        received_at: datetime | None = None,
        trace_id: str | None = None,
    ) -> ReceiverResult:
        start = time.perf_counter()
        trace = trace_id or uuid.uuid4().hex
        event_name = self._headers(raw_headers).get("x-github-event", "unknown")[:64]
        delivery_id = self._headers(raw_headers).get("x-github-delivery")

        if not self.policy.enabled:
            return self._result(
                start=start,
                event=event_name,
                status_code=503,
                result="disabled",
                trace_id=trace,
                delivery_id=delivery_id,
                error_code="RECEIVER_DISABLED",
            )
        if len(raw_body) > self.policy.max_body_bytes:
            return self._result(
                start=start,
                event=event_name,
                status_code=413,
                result="rejected",
                trace_id=trace,
                delivery_id=delivery_id,
                error_code="BODY_TOO_LARGE",
            )

        try:
            headers = self._parse_headers(raw_headers)
            key_id = verify_signature(raw_body, headers.signature_256, self.secrets)
            payload_hash = payload_sha256(raw_body)
            payload = loads_json_object(raw_body)
            envelope = normalize_delivery(
                headers=headers,
                payload=payload,
                payload_sha256=payload_hash,
                policy=self.policy,
                key_id=key_id,
                trace_id=trace,
                received_at=received_at or datetime.now(UTC),
            )
            outcome = self.store.store_delivery(envelope, self.policy.dispatch_handlers)
        except WebhookSecurityError as exc:
            status_code = {
                "CONTENT_TYPE_MISSING": 415,
                "CONTENT_TYPE_UNSUPPORTED": 415,
                "JSON_INVALID": 400,
                "JSON_ROOT_NOT_OBJECT": 400,
                "BODY_NOT_UTF8": 400,
                "DELIVERY_ID_MISSING": 400,
                "HEADERS_INVALID": 400,
                "EVENT_HEADER_MISSING": 400,
                "EVENT_NOT_ALLOWED": 422,
            }.get(exc.code, 401)
            return self._result(
                start=start,
                event=event_name,
                status_code=status_code,
                result="rejected",
                trace_id=trace,
                delivery_id=delivery_id,
                error_code=exc.code,
                signature_failure=exc.code.startswith("SIGNATURE"),
            )
        except DuplicateJsonKeyError:
            return self._result(
                start=start,
                event=event_name,
                status_code=400,
                result="rejected",
                trace_id=trace,
                delivery_id=delivery_id,
                error_code="JSON_DUPLICATE_KEY",
            )
        except WebhookNormalizationError as exc:
            status_code = 403 if exc.code == "REPOSITORY_NOT_ALLOWED" else 422
            return self._result(
                start=start,
                event=event_name,
                status_code=status_code,
                result="rejected",
                trace_id=trace,
                delivery_id=delivery_id,
                error_code=exc.code,
            )
        except (sqlite3.Error, OSError):
            return self._result(
                start=start,
                event=event_name,
                status_code=503,
                result="unavailable",
                trace_id=trace,
                delivery_id=delivery_id,
                error_code="STORE_UNAVAILABLE",
            )

        delivery = str(envelope.delivery_id)
        if outcome is StoreOutcome.ACCEPTED:
            return self._result(
                start=start,
                event=headers.event_type.value,
                status_code=202,
                result="accepted",
                trace_id=trace,
                delivery_id=delivery,
                processing_status="QUEUED",
            )
        if outcome is StoreOutcome.DUPLICATE:
            return self._result(
                start=start,
                event=headers.event_type.value,
                status_code=200,
                result="duplicate",
                trace_id=trace,
                delivery_id=delivery,
                processing_status="QUEUED",
                duplicate_result="same_hash",
            )
        return self._result(
            start=start,
            event=headers.event_type.value,
            status_code=409,
            result="conflict",
            trace_id=trace,
            delivery_id=delivery,
            error_code="DELIVERY_ID_HASH_CONFLICT",
            duplicate_result="hash_conflict",
        )

    def health(self) -> dict[str, Any]:
        store_ready = self.store.health()
        return {
            "status": "ready" if self.policy.enabled and store_ready else "not_ready",
            "enabled": self.policy.enabled,
            "store_ready": store_ready,
            "queue_depth": self.store.queue_depth() if store_ready else None,
            "raw_payload_persistence": False,
            "adapters_enabled": False,
        }
