from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loto.adapters.timer_s1.contracts import ProviderStatus, TimerS1Request
from loto.timer_s1_campaign.provider import handle_request


def payload(operation: str) -> dict[str, object]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    history = [
        {
            "timestamp": (start + timedelta(days=index)).isoformat(),
            "values": [float(index + position) for position in range(7)],
            "future_actual": False,
        }
        for index in range(2)
    ]
    return {
        "schema_version": 1,
        "run_id": f"provider-{operation}",
        "operation": operation,
        "model_id": "timer-s1",
        "model_repo": "bytedance-research/Timer-S1",
        "package_version": "UNVERIFIED",
        "source_revision": "UNPINNED",
        "model_revision": "UNPINNED",
        "config_sha256": "UNPINNED",
        "weight_sha256": "UNPINNED",
        "weight_manifest_sha256": "UNPINNED",
        "license": "Apache-2.0",
        "game": "loto7",
        "target_layout": "position_univariate",
        "batch_semantics": "independent_series",
        "joint_multivariate": False,
        "timeline_mode": "draw-sequence",
        "context_length": 2,
        "prediction_length": 1,
        "seed": 1,
        "requested_device": "cpu",
        "history": [] if operation == "identity" else history,
        "past_covariates": None,
        "known_future_covariates": None,
        "snapshot_path": None,
        "manifest_path": None,
        "remote_code_review_path": None,
    }


def test_identity_is_execution_pending_not_runtime_success() -> None:
    response = handle_request(TimerS1Request.model_validate(payload("identity")))
    assert response.status is ProviderStatus.EXECUTION_PENDING
    assert response.runtime_verified is False
    assert response.error_code == "PR_A_PROVIDER_SKELETON"


def test_predict_without_reviewed_manifest_stops_before_model_load() -> None:
    response = handle_request(TimerS1Request.model_validate(payload("predict")))
    assert response.status is ProviderStatus.EXECUTION_PENDING
    assert response.runtime_verified is False
    assert response.error_code == "MANIFEST_REQUIRED"
    assert response.actuals_used is False
