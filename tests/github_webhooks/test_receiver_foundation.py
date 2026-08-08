from __future__ import annotations

import hashlib
import hmac
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, generate_latest
from pydantic import ValidationError

from loto.github_webhooks.api import create_github_webhook_router
from loto.github_webhooks.config import load_receiver_policy
from loto.github_webhooks.contracts import HandlerStatus, ReceiverPolicy
from loto.github_webhooks.metrics import create_metrics
from loto.github_webhooks.normalization import classify_workflow_execution
from loto.github_webhooks.security import (
    SecretKey,
    SecretRing,
    WebhookSecurityError,
    verify_signature,
)
from loto.github_webhooks.service import ReceiverService
from loto.github_webhooks.store import WebhookStore

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "github_webhooks" / "receiver_v1.yaml"
DELIVERY_ID = UUID("11111111-2222-4333-8444-555555555555")
SECRET = hashlib.sha256(b"github-webhook-test-fixture").digest()
RECEIVED_AT = datetime(2026, 8, 6, 9, 30, tzinfo=UTC)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def issue_payload(*, title: str = "ignored raw title") -> dict[str, object]:
    return {
        "action": "opened",
        "repository": {
            "id": 1317186795,
            "full_name": "arumajirou/loto_forecast_platform",
            "private": True,
        },
        "sender": {"login": "fixture-user", "email": "not-persisted@example.invalid"},
        "issue": {
            "number": 7,
            "state": "open",
            "state_reason": None,
            "title": title,
            "body": "raw body must not be persisted",
            "labels": [{"name": "test"}],
            "assignees": [],
            "user": {"login": "fixture-user"},
            "html_url": "https://github.com/arumajirou/loto_forecast_platform/issues/7",
        },
    }


def signed_headers(
    raw_body: bytes,
    *,
    delivery_id: UUID = DELIVERY_ID,
    secret: bytes = SECRET,
    event: str = "issues",
    content_type: str = "application/json",
) -> dict[str, str]:
    signature = "sha256=" + hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": str(delivery_id),
        "X-Hub-Signature-256": signature,
        "User-Agent": "GitHub-Hookshot/test",
    }


def enabled_policy() -> ReceiverPolicy:
    return load_receiver_policy(POLICY_PATH).model_copy(update={"enabled": True})


def build_service(tmp_path: Path, *, metrics=False) -> tuple[ReceiverService, WebhookStore]:
    policy = enabled_policy()
    store = WebhookStore(
        tmp_path / "receiver.sqlite3",
        max_attempts=policy.max_attempts,
        base_backoff_seconds=policy.base_backoff_seconds,
        max_backoff_seconds=policy.max_backoff_seconds,
    )
    metric_set = create_metrics(CollectorRegistry()) if metrics else None
    service = ReceiverService(
        policy=policy,
        secrets=SecretRing(
            active=SecretKey("active-v1", SECRET),
            previous=SecretKey("previous-v0", b"previous-fixture-secret"),
        ),
        store=store,
        metrics=metric_set,
        logger=logging.getLogger("webhook-test"),
    )
    return service, store


def test_policy_is_disabled_by_default_and_strict(tmp_path: Path) -> None:
    policy = load_receiver_policy(POLICY_PATH)
    assert policy.enabled is False
    assert policy.forensic_raw_payload_enabled is False
    assert set(event.value for event in policy.allowed_actions) == {
        "push",
        "pull_request",
        "issues",
        "workflow_run",
    }

    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_receiver_policy(bad)


@pytest.mark.parametrize(
    "header,code",
    [
        (None, "SIGNATURE_MISSING"),
        ("sha1=" + "0" * 40, "SIGNATURE_MALFORMED"),
        ("sha256=" + "0" * 63, "SIGNATURE_MALFORMED"),
        ("sha256=" + "z" * 64, "SIGNATURE_MALFORMED"),
    ],
)
def test_signature_header_failures(header: str | None, code: str) -> None:
    with pytest.raises(WebhookSecurityError, match=code):
        verify_signature(
            b"{}",
            header,
            SecretRing(SecretKey("active", SECRET)),
        )


def test_signature_rotation_accepts_active_and_previous() -> None:
    raw = b'{"ok":true}'
    previous_secret = b"previous-fixture-secret"
    ring = SecretRing(
        active=SecretKey("active-v1", SECRET),
        previous=SecretKey("previous-v0", previous_secret),
    )
    active = "sha256=" + hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
    previous = "sha256=" + hmac.new(previous_secret, raw, hashlib.sha256).hexdigest()
    assert verify_signature(raw, active, ring) == "active-v1"
    assert verify_signature(raw, previous, ring) == "previous-v0"


def test_invalid_signature_is_rejected_before_json_parsing(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    raw = b'{"broken":'
    headers = signed_headers(raw)
    headers["X-Hub-Signature-256"] = "sha256=" + "0" * 64
    result = service.receive(raw_body=raw, raw_headers=headers, trace_id="a" * 32)
    assert result.status_code == 401
    assert result.error_code == "SIGNATURE_INVALID"
    assert store.delivery_count() == 0


def test_valid_delivery_is_persisted_and_duplicate_is_idempotent(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    raw = canonical_json(issue_payload())
    headers = signed_headers(raw)

    first = service.receive(
        raw_body=raw,
        raw_headers=headers,
        received_at=RECEIVED_AT,
        trace_id="1" * 32,
    )
    duplicate = service.receive(
        raw_body=raw,
        raw_headers=headers,
        received_at=RECEIVED_AT,
        trace_id="2" * 32,
    )

    assert first.status_code == 202
    assert first.result == "accepted"
    assert duplicate.status_code == 200
    assert duplicate.result == "duplicate"
    assert store.delivery_count() == 1
    assert store.outbox_count() == 1
    row = store.get_delivery(1317186795, str(DELIVERY_ID))
    assert row is not None
    assert row["status"] == "QUEUED"
    persisted = str(row["normalized_json"])
    assert "raw body must not be persisted" not in persisted
    assert "not-persisted@example.invalid" not in persisted
    assert "X-Hub-Signature-256" not in persisted
    assert SECRET.hex() not in persisted


def test_delivery_id_reuse_with_changed_hash_is_conflict(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    first_raw = canonical_json(issue_payload(title="first"))
    second_raw = canonical_json(issue_payload(title="second"))

    first = service.receive(
        raw_body=first_raw,
        raw_headers=signed_headers(first_raw),
        received_at=RECEIVED_AT,
        trace_id="3" * 32,
    )
    conflict = service.receive(
        raw_body=second_raw,
        raw_headers=signed_headers(second_raw),
        received_at=RECEIVED_AT,
        trace_id="4" * 32,
    )

    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.error_code == "DELIVERY_ID_HASH_CONFLICT"
    assert store.delivery_count() == 1
    assert store.outbox_count() == 1


@pytest.mark.parametrize(
    ("headers_mutation", "raw", "expected_status", "expected_code"),
    [
        ({"Content-Type": "text/plain"}, b"{}", 415, "CONTENT_TYPE_UNSUPPORTED"),
        ({}, b"not-json", 400, "JSON_INVALID"),
    ],
)
def test_content_and_json_failures(
    tmp_path: Path,
    headers_mutation: dict[str, str],
    raw: bytes,
    expected_status: int,
    expected_code: str,
) -> None:
    service, store = build_service(tmp_path)
    headers = signed_headers(raw)
    headers.update(headers_mutation)
    result = service.receive(raw_body=raw, raw_headers=headers, trace_id="5" * 32)
    assert result.status_code == expected_status
    assert result.error_code == expected_code
    assert store.delivery_count() == 0


def test_duplicate_json_key_and_oversized_body_fail_closed(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    duplicate_key = (
        b'{"action":"opened","action":"closed","repository":{"id":1317186795,'
        b'"full_name":"arumajirou/loto_forecast_platform"}}'
    )
    duplicate = service.receive(
        raw_body=duplicate_key,
        raw_headers=signed_headers(duplicate_key),
        trace_id="6" * 32,
    )
    assert duplicate.status_code == 400
    assert duplicate.error_code == "JSON_DUPLICATE_KEY"

    oversized = b"x" * (enabled_policy().max_body_bytes + 1)
    too_large = service.receive(
        raw_body=oversized,
        raw_headers=signed_headers(oversized),
        trace_id="7" * 32,
    )
    assert too_large.status_code == 413
    assert too_large.error_code == "BODY_TOO_LARGE"
    assert store.delivery_count() == 0


def test_unsupported_event_header_is_rejected_as_unprocessable(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    raw = canonical_json(issue_payload())
    result = service.receive(
        raw_body=raw,
        raw_headers=signed_headers(raw, event="deployment"),
        trace_id="e" * 32,
    )
    assert result.status_code == 422
    assert result.error_code == "EVENT_NOT_ALLOWED"
    assert store.delivery_count() == 0


def test_repository_and_action_allowlists_fail_closed(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    wrong_repo = issue_payload()
    wrong_repo["repository"] = {"id": 1, "full_name": "octocat/Hello-World"}
    raw = canonical_json(wrong_repo)
    result = service.receive(
        raw_body=raw,
        raw_headers=signed_headers(raw),
        trace_id="8" * 32,
    )
    assert result.status_code == 403
    assert result.error_code == "REPOSITORY_NOT_ALLOWED"

    unsupported = issue_payload()
    unsupported["action"] = "transferred"
    raw_unsupported = canonical_json(unsupported)
    result_unsupported = service.receive(
        raw_body=raw_unsupported,
        raw_headers=signed_headers(raw_unsupported),
        trace_id="9" * 32,
    )
    assert result_unsupported.status_code == 422
    assert result_unsupported.error_code == "ACTION_NOT_ALLOWED"
    assert store.delivery_count() == 0


def test_concurrent_identical_deliveries_create_one_record(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    raw = canonical_json(issue_payload())
    headers = signed_headers(raw)

    def send(index: int):
        return service.receive(
            raw_body=raw,
            raw_headers=headers,
            received_at=RECEIVED_AT,
            trace_id=f"{index:032x}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(send, range(1, 9)))

    assert sum(result.status_code == 202 for result in results) == 1
    assert sum(result.status_code == 200 for result in results) == 7
    assert store.delivery_count() == 1
    assert store.outbox_count() == 1


def test_retry_dead_letter_and_restart_recovery(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    raw = canonical_json(issue_payload())
    result = service.receive(
        raw_body=raw,
        raw_headers=signed_headers(raw),
        received_at=RECEIVED_AT,
        trace_id="b" * 32,
    )
    assert result.status_code == 202

    claim = store.claim_ready(worker_id="worker-1", now=RECEIVED_AT)[0]
    retry = store.complete_claim(
        claim,
        success=False,
        transient=True,
        error_code="TEMPORARY_FAILURE",
        now=RECEIVED_AT,
    )
    assert retry is HandlerStatus.RETRY
    assert store.claim_ready(worker_id="worker-2", now=RECEIVED_AT) == []

    future = RECEIVED_AT + timedelta(hours=2)
    second_claim = store.claim_ready(worker_id="worker-2", now=future)[0]
    assert second_claim.attempt == 2

    recovered = store.recover_processing(
        before=future + timedelta(seconds=1),
        now=future + timedelta(seconds=2),
    )
    assert recovered == 1
    third_claim = store.claim_ready(
        worker_id="worker-3",
        now=future + timedelta(seconds=3),
    )[0]
    assert third_claim.attempt == 3

    final = store.complete_claim(
        third_claim,
        success=False,
        transient=False,
        error_code="PERMANENT_FAILURE",
        now=future + timedelta(seconds=4),
    )
    assert final is HandlerStatus.DEAD_LETTER
    assert store.dead_letter_count() == 1
    row = store.get_delivery(1317186795, str(DELIVERY_ID))
    assert row is not None and row["status"] == "DEAD_LETTER"


def test_successful_handler_marks_delivery_processed(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    raw = canonical_json(issue_payload())
    service.receive(
        raw_body=raw,
        raw_headers=signed_headers(raw),
        received_at=RECEIVED_AT,
        trace_id="c" * 32,
    )
    claim = store.claim_ready(worker_id="worker-success", now=RECEIVED_AT)[0]
    status = store.complete_claim(claim, success=True, now=RECEIVED_AT)
    assert status is HandlerStatus.SUCCEEDED
    row = store.get_delivery(1317186795, str(DELIVERY_ID))
    assert row is not None and row["status"] == "PROCESSED"
    assert store.queue_depth() == 0


def test_workflow_execution_classification_preserves_pre_run_blocker() -> None:
    assert (
        classify_workflow_execution(steps=None, logs_available=False, conclusion="failure")
        == "CI_BLOCKED_PRE_RUN"
    )
    assert (
        classify_workflow_execution(
            steps=[{"name": "checkout"}],
            logs_available=True,
            conclusion="failure",
        )
        == "ACTIONS_FAILED_ACTIONABLE"
    )
    assert (
        classify_workflow_execution(
            steps=[{"name": "checkout"}],
            logs_available=True,
            conclusion="success",
        )
        == "ACTIONS_VERIFIED"
    )


def test_fastapi_contract_and_disabled_health(tmp_path: Path) -> None:
    service, store = build_service(tmp_path)
    app = FastAPI()
    app.include_router(create_github_webhook_router(service))
    client = TestClient(app)
    raw = canonical_json(issue_payload())
    response = client.post("/webhooks/github", content=raw, headers=signed_headers(raw))
    assert response.status_code == 202
    assert response.json()["result"] == "accepted"
    assert "status_code" not in response.json()
    health = client.get("/webhooks/github/health")
    assert health.status_code == 200
    assert health.json()["raw_payload_persistence"] is False
    assert health.json()["adapters_enabled"] is False

    disabled = ReceiverService(
        policy=load_receiver_policy(POLICY_PATH),
        secrets=SecretRing(SecretKey("active", SECRET)),
        store=store,
    )
    disabled_app = FastAPI()
    disabled_app.include_router(create_github_webhook_router(disabled))
    disabled_client = TestClient(disabled_app)
    disabled_response = disabled_client.post(
        "/webhooks/github",
        content=raw,
        headers=signed_headers(raw),
    )
    assert disabled_response.status_code == 503
    assert disabled_response.json()["error_code"] == "RECEIVER_DISABLED"


def test_metrics_use_only_bounded_labels(tmp_path: Path) -> None:
    registry = CollectorRegistry()
    policy = enabled_policy()
    store = WebhookStore(
        tmp_path / "metrics.sqlite3",
        max_attempts=policy.max_attempts,
        base_backoff_seconds=policy.base_backoff_seconds,
        max_backoff_seconds=policy.max_backoff_seconds,
    )
    metrics = create_metrics(registry)
    service = ReceiverService(
        policy=policy,
        secrets=SecretRing(SecretKey("active", SECRET)),
        store=store,
        metrics=metrics,
    )
    raw = canonical_json(issue_payload())
    service.receive(
        raw_body=raw,
        raw_headers=signed_headers(raw),
        received_at=RECEIVED_AT,
        trace_id="d" * 32,
    )
    exposition = generate_latest(registry).decode("utf-8")
    assert "github_webhook_requests_total" in exposition
    assert 'event="issues"' in exposition
    assert 'result="accepted"' in exposition
    assert str(DELIVERY_ID) not in exposition
    assert "fixture-user" not in exposition
    assert "arumajirou/loto_forecast_platform" not in exposition
