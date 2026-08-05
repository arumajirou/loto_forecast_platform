from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from loto.sktime_campaign.prospective import (
    ObservedHistory,
    ProspectiveActuals,
    ProspectiveMonitoringRequest,
    ProspectiveRequest,
)
from loto.sktime_campaign.prospective_artifacts import (
    P4LineageContext,
    P5VerificationError,
    persist_prospective_lock,
    persist_prospective_monitor,
    verify_prospective_bundle,
    verify_prospective_monitor,
)


def make_request(output_dir: Path) -> ProspectiveRequest:
    return ProspectiveRequest(
        output_dir=str(output_dir),
        run_id="p5-artifact-test",
        git_commit="abcdef1",
        code_sha256="1" * 64,
        config_sha256="2" * 64,
        p4_artifact_sha256="3" * 64,
        p4_selected_oof_candidate_id="naive_last",
        p4_promotion_status="NOT_PROMOTED",
        history=ObservedHistory(
            game_id="numbers3-synthetic-contract",
            draw_no=list(range(1001, 1031)),
            position_names=["N1", "N2", "N3"],
            values=[
                [
                    float(index % 10),
                    float((index + 1) % 10),
                    float((index + 2) % 10),
                ]
                for index in range(30)
            ],
            legal_min=[0, 0, 0],
            legal_max=[9, 9, 9],
        ),
        prospective_draw_no=[1031, 1032, 1033],
        max_workers=8,
    )


def context() -> P4LineageContext:
    return P4LineageContext(
        p4_status="PASS",
        p4_promotion_status="NOT_PROMOTED",
        p4_selected_oof_candidate_id="naive_last",
        p4_response_file_sha256="4" * 64,
        p4_sha256sums_sha256="5" * 64,
        p4_candidate_aggregates_file_sha256="6" * 64,
    )


def model_predictor(model_id, history, horizon, request):
    del request
    offset = {
        "naive_last": 0.0,
        "polynomial_trend_d1": 1.0,
        "exponential_smoothing": 2.0,
        "theta": 3.0,
    }[model_id.value]
    return {
        "candidate_kind": "sktime",
        "candidate_id": model_id.value,
        "status": "PASS",
        "raw_predictions": np.tile(history[-1] + offset, (horizon, 1)).tolist(),
    }


def set_thread_limits(monkeypatch) -> None:
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "1")


def make_lock_bundle(tmp_path: Path, monkeypatch):
    set_thread_limits(monkeypatch)
    output_dir = tmp_path / "lock"
    request = make_request(output_dir)
    persist_prospective_lock(
        request,
        context(),
        sealed_at_utc="2026-08-05T00:00:00Z",
        model_predictor=model_predictor,
    )
    lock = json.loads(
        (output_dir / "PROSPECTIVE_PREDICTION_LOCK.json").read_text(
            encoding="utf-8"
        )
    )
    return output_dir, request, lock


def make_monitor_request(lock: dict, *, values=None):
    return ProspectiveMonitoringRequest(
        run_id="p5-monitor-artifact-test",
        prediction_lock=lock,
        actuals=ProspectiveActuals(
            game_id="numbers3-synthetic-contract",
            revealed_at_utc="2026-08-05T00:00:01Z",
            source_id="synthetic-contract",
            source_sha256="7" * 64,
            draw_no=[1031, 1032, 1033],
            position_names=["N1", "N2", "N3"],
            values=values
            or [
                [0.0, 1.0, 2.0],
                [1.0, 2.0, 3.0],
                [2.0, 3.0, 4.0],
            ],
        ),
        holdout_reference_metrics={
            "hit_at_1": {"mean": 0.95, "variance": 0.0, "worst": 0.95},
            "mae": {"mean": 0.2, "variance": 0.0, "worst": 0.2},
        },
    )


def test_persist_and_verify_formal_lock_bundle(tmp_path, monkeypatch) -> None:
    output_dir, request, _ = make_lock_bundle(tmp_path, monkeypatch)
    report = verify_prospective_bundle(
        output_dir,
        request,
        context(),
        formal=True,
    )
    assert report["status"] == "PASS"
    assert report["candidate_seed_count"] == 13
    assert report["max_workers"] == 8


def test_lock_bundle_redacts_history_values(tmp_path, monkeypatch) -> None:
    output_dir, _, _ = make_lock_bundle(tmp_path, monkeypatch)
    metadata = json.loads(
        (output_dir / "REQUEST_METADATA.json").read_text(encoding="utf-8")
    )
    assert metadata["history"]["values"].startswith("REDACTED")


def test_lock_bundle_detects_prediction_tamper(tmp_path, monkeypatch) -> None:
    output_dir, request, _ = make_lock_bundle(tmp_path, monkeypatch)
    path = output_dir / "PROSPECTIVE_PREDICTION_LOCK.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["prediction_rows"][0]["predictions"][0][0] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((P5VerificationError, ValueError)):
        verify_prospective_bundle(output_dir, request, context(), formal=True)


def test_lock_bundle_detects_manifest_tamper(tmp_path, monkeypatch) -> None:
    output_dir, request, _ = make_lock_bundle(tmp_path, monkeypatch)
    path = output_dir / "HISTORY_CONTRACT.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(P5VerificationError):
        verify_prospective_bundle(output_dir, request, context(), formal=True)


def test_persist_and_verify_monitor_bundle(tmp_path, monkeypatch) -> None:
    _, _, lock = make_lock_bundle(tmp_path, monkeypatch)
    output_dir = tmp_path / "monitor"
    request = make_monitor_request(lock)
    persist_prospective_monitor(request, output_dir)
    report = verify_prospective_monitor(output_dir, request, formal=True)
    assert report["status"] == "PASS"
    assert report["promotion_status"] == "NOT_PROMOTED"
    assert report["automatic_retraining"] is False


def test_critical_drift_still_produces_verified_evidence(tmp_path, monkeypatch) -> None:
    _, _, lock = make_lock_bundle(tmp_path, monkeypatch)
    output_dir = tmp_path / "critical-monitor"
    request = make_monitor_request(lock, values=[[9.0, 9.0, 9.0]] * 3)
    response = persist_prospective_monitor(request, output_dir)
    report = verify_prospective_monitor(output_dir, request, formal=True)
    assert response["drift_status"] == "CRITICAL"
    assert report["status"] == "PASS"
    assert report["recommendation"] == (
        "BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED"
    )


def test_monitor_bundle_detects_metric_tamper(tmp_path, monkeypatch) -> None:
    _, _, lock = make_lock_bundle(tmp_path, monkeypatch)
    output_dir = tmp_path / "tampered-monitor"
    request = make_monitor_request(lock)
    persist_prospective_monitor(request, output_dir)
    path = output_dir / "PROSPECTIVE_RESULTS.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["metrics"]["hit_at_1"] = 0.123
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(P5VerificationError):
        verify_prospective_monitor(output_dir, request, formal=True)


def test_monitor_never_records_automatic_promotion(tmp_path, monkeypatch) -> None:
    _, _, lock = make_lock_bundle(tmp_path, monkeypatch)
    output_dir = tmp_path / "no-promotion"
    request = make_monitor_request(lock)
    persist_prospective_monitor(request, output_dir)
    response = json.loads(
        (output_dir / "response.json").read_text(encoding="utf-8")
    )
    assert response["automatic_promotion"] is False
    assert response["automatic_retraining"] is False
    assert response["promotion_status"] == "NOT_PROMOTED"
