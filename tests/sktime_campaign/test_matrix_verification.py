from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loto.sktime_campaign.matrix_verification import (
    FORMAL_P1_MODEL_IDS,
    verify_matrix_bundle,
)
from loto.sktime_campaign.verification import VerificationError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _finalize_bundle(directory: Path) -> None:
    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    _write_json(
        directory / "ARTIFACT_MANIFEST.json",
        {
            "status": "PASS",
            "files": [
                {
                    "path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in files
            ],
        },
    )
    hashed = sorted(
        path for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    (directory / "SHA256SUMS").write_text(
        "\n".join(f"{_sha256(path)}  {path.name}" for path in hashed) + "\n"
    )


def _matrix_bundle(directory: Path) -> None:
    directory.mkdir()
    results = []
    for model_id in FORMAL_P1_MODEL_IDS:
        archive = directory / f"{model_id}_model.zip"
        archive.write_bytes(b"PK-test-" + model_id.encode())
        values = [3.0, 4.0]
        results.append(
            {
                "model_id": model_id,
                "status": "PASS",
                "device": "cpu",
                "cpu_fallback": False,
                "dependency_status": "PASS",
                "import_status": "PASS",
                "construct_status": "PASS",
                "fit_status": "PASS",
                "predict_status": "PASS",
                "save_load_status": "PASS",
                "prediction_finite": True,
                "forecast_horizon": [1, 2],
                "expected_prediction_index": [9, 10],
                "prediction_shape": [2],
                "prediction_before_save": values,
                "prediction_after_load": values,
                "save_load": {
                    "status": "PASS",
                    "exact_prediction_match": True,
                    "artifact": archive.name,
                    "artifact_sha256": _sha256(archive),
                },
            }
        )
    matrix = {
        "status": "PASS",
        "device": "cpu",
        "cpu_fallback": False,
        "requested_model_ids": list(FORMAL_P1_MODEL_IDS),
        "summary": {
            "status": "PASS",
            "total": len(FORMAL_P1_MODEL_IDS),
            "counts": {
                "PASS": len(FORMAL_P1_MODEL_IDS),
                "PARTIAL": 0,
                "FAILED": 0,
                "UNAVAILABLE": 0,
            },
            "all_requested_models_passed": True,
        },
        "results": results,
    }
    _write_json(directory / "SMOKE_MATRIX.json", matrix)
    _write_json(
        directory / "response.json",
        {
            "status": "PASS",
            "operation": "smoke_matrix",
            "environment_lane": "classic-py312",
            "expected_sktime_version": "1.0.1",
            "actual_sktime_version": "1.0.1",
            "matrix": matrix,
        },
    )
    _finalize_bundle(directory)


def test_verify_matrix_bundle_passes(tmp_path: Path) -> None:
    bundle = tmp_path / "smoke-matrix"
    _matrix_bundle(bundle)

    report = verify_matrix_bundle(bundle)

    assert report["status"] == "PASS"
    assert report["passed"] == len(FORMAL_P1_MODEL_IDS)


def test_verify_matrix_bundle_rejects_partial_status(tmp_path: Path) -> None:
    bundle = tmp_path / "smoke-matrix"
    _matrix_bundle(bundle)
    response = json.loads((bundle / "response.json").read_text())
    response["status"] = "PARTIAL"
    _write_json(bundle / "response.json", response)
    _finalize_bundle(bundle)

    with pytest.raises(VerificationError, match="not PASS"):
        verify_matrix_bundle(bundle)


def test_verify_matrix_bundle_rejects_model_archive_tamper(tmp_path: Path) -> None:
    bundle = tmp_path / "smoke-matrix"
    _matrix_bundle(bundle)
    archive = bundle / f"{FORMAL_P1_MODEL_IDS[0]}_model.zip"
    archive.write_bytes(b"tampered")

    with pytest.raises(VerificationError, match="SHA-256 mismatch"):
        verify_matrix_bundle(bundle)
