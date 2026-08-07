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


def complete_manifest(tmp_path):
    from pathlib import Path

    from loto.timer_s1_campaign.model_manifest import (
        ArtifactRecord,
        TimerS1ModelManifest,
    )

    artifacts = (
        ArtifactRecord(
            path="config.json",
            size_bytes=1,
            sha256="c" * 64,
            kind="config",
        ),
        ArtifactRecord(
            path="model.safetensors.index.json",
            size_bytes=1,
            sha256="d" * 64,
            kind="weight-index",
        ),
        *tuple(
            ArtifactRecord(
                path=f"model-{index:05d}-of-00004.safetensors",
                size_bytes=index,
                sha256=f"{index}" * 64,
                kind="weight",
            )
            for index in range(1, 5)
        ),
        ArtifactRecord(
            path="configuration_TimerS1.py",
            size_bytes=1,
            sha256="a" * 64,
            kind="remote-code",
        ),
        ArtifactRecord(
            path="modeling_TimerS1.py",
            size_bytes=1,
            sha256="b" * 64,
            kind="remote-code",
        ),
        ArtifactRecord(
            path="ts_generation_mixin.py",
            size_bytes=1,
            sha256="e" * 64,
            kind="remote-code",
        ),
    )
    manifest = TimerS1ModelManifest(
        schema_version=1,
        model_id="timer-s1",
        canonical_repo="bytedance-research/Timer-S1",
        mirror_repo="thuml/Timer-S1",
        arxiv_id="2603.04791",
        license="Apache-2.0",
        gated=False,
        trust_remote_code=True,
        model_revision="a" * 40,
        source_revision="b" * 40,
        observed_model_revision="a" * 40,
        observed_source_revision="b" * 40,
        mirror_revision="UNPINNED",
        package_versions={},
        python_compatibility="TEST",
        artifacts=artifacts,
        mirror_fallback_enabled=False,
    )
    path = Path(tmp_path) / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path, manifest


def pinned_payload(tmp_path, **overrides: object) -> dict[str, object]:
    path, manifest = complete_manifest(tmp_path)
    data = payload("predict")
    data.update(
        {
            "model_revision": manifest.model_revision,
            "source_revision": manifest.source_revision,
            "config_sha256": manifest.artifact_sha256("config.json"),
            "weight_manifest_sha256": manifest.artifact_sha256(
                "model.safetensors.index.json"
            ),
            "weight_sha256": manifest.weight_set_sha256,
            "manifest_path": str(path.resolve()),
        }
    )
    data.update(overrides)
    return data


def test_complete_manifest_binds_all_request_hashes(tmp_path) -> None:
    response = handle_request(TimerS1Request.model_validate(pinned_payload(tmp_path)))
    assert response.status is ProviderStatus.EXECUTION_PENDING
    assert response.error_code == "REAL_RUNTIME_DEFERRED_TO_PR_B"


def test_config_hash_must_match_manifest(tmp_path) -> None:
    response = handle_request(
        TimerS1Request.model_validate(
            pinned_payload(tmp_path, config_sha256="f" * 64)
        )
    )
    assert response.error_code == "CONFIG_SHA256_MISMATCH"


def test_weight_set_hash_must_match_manifest(tmp_path) -> None:
    response = handle_request(
        TimerS1Request.model_validate(
            pinned_payload(tmp_path, weight_sha256="f" * 64)
        )
    )
    assert response.error_code == "WEIGHT_SHA256_MISMATCH"


def test_invalid_request_failure_run_id_is_sanitized() -> None:
    from scripts.run_timer_s1_provider import _failure_run_id

    assert _failure_run_id({"run_id": "../unsafe"}) == "invalid-request"
    assert _failure_run_id({"run_id": "safe-run_1"}) == "safe-run_1"
