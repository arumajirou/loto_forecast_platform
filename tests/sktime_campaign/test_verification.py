from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loto.sktime_campaign.verification import (
    VerificationError,
    finalize_p0_run,
    verify_inventory_bundle,
    verify_sha256sums,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _finalize_provider_bundle(directory: Path, *, status: str, operation: str) -> None:
    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    _write_json(
        directory / "ARTIFACT_MANIFEST.json",
        {
            "schema_version": "1.0",
            "status": status,
            "operation": operation,
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
        "\n".join(f"{_sha256(path)}  {path.name}" for path in hashed) + "\n",
        encoding="utf-8",
    )


def _inventory_bundle(directory: Path) -> None:
    directory.mkdir(parents=True)
    rows = [
        {
            "name": "NaiveForecaster",
            "dependency_state": "CORE_COMPATIBLE",
            "import_status": "IMPORTABLE",
        },
        {
            "name": "ThetaForecaster",
            "dependency_state": "OPTIONAL_DEPENDENCY_DECLARED",
            "import_status": "IMPORTABLE",
        },
    ]
    summary = {
        "discovered": 2,
        "importable": 2,
        "core_compatible": 1,
        "optional_dependency_declared": 1,
        "constructable": 0,
        "runtime_verified": 0,
        "count_source": "sktime.registry.all_estimators('forecaster')",
    }
    _write_json(directory / "FORECASTER_INVENTORY.json", rows)
    (directory / "FORECASTER_INVENTORY.csv").write_text(
        "name\nNaiveForecaster\nThetaForecaster\n",
        encoding="utf-8",
    )
    _write_json(directory / "INVENTORY_SUMMARY.json", summary)
    _write_json(
        directory / "response.json",
        {
            "status": "PASS",
            "operation": "inventory",
            "expected_sktime_version": "1.0.1",
            "actual_sktime_version": "1.0.1",
            "inventory": summary,
        },
    )
    _finalize_provider_bundle(directory, status="PASS", operation="inventory")


def _naive_bundle(directory: Path) -> None:
    directory.mkdir(parents=True)
    archive = directory / "naive_forecaster.zip"
    archive.write_bytes(b"PK\x03\x04test-model")
    smoke = {
        "model_name": "NaiveForecaster",
        "strategy": "last",
        "device": "cpu",
        "cpu_fallback": False,
        "forecast_horizon": [1, 2],
        "prediction_shape": [2],
        "prediction_finite": True,
        "prediction_before_save": [10.0, 10.0],
        "prediction_after_load": [10.0, 10.0],
        "fit_status": "PASS",
        "predict_status": "PASS",
        "save_load": {
            "requested": True,
            "status": "PASS",
            "artifact": archive.name,
            "artifact_sha256": _sha256(archive),
            "exact_prediction_match": True,
        },
    }
    _write_json(directory / "NAIVE_SMOKE.json", smoke)
    _write_json(
        directory / "response.json",
        {
            "status": "PASS",
            "operation": "naive_smoke",
            "expected_sktime_version": "1.0.1",
            "actual_sktime_version": "1.0.1",
            "smoke": smoke,
        },
    )
    _finalize_provider_bundle(directory, status="PASS", operation="naive_smoke")


def test_finalize_p0_run_verifies_nested_bundles(tmp_path: Path) -> None:
    _inventory_bundle(tmp_path / "inventory")
    _naive_bundle(tmp_path / "naive-smoke")
    (tmp_path / "RUN_METADATA.txt").write_text("git_head=test\n", encoding="utf-8")

    report = finalize_p0_run(tmp_path)

    assert report["status"] == "PASS"
    assert report["inventory"]["discovered"] == 2
    assert report["naive_smoke"]["save_load"] == "PASS"
    assert (tmp_path / "VERIFICATION_REPORT.json").is_file()
    assert (tmp_path / "ARTIFACT_MANIFEST.json").is_file()
    records = verify_sha256sums(tmp_path, recursive=True)
    assert len(records) == report["top_level_sha256_records"]


def test_inventory_verification_fails_after_tamper(tmp_path: Path) -> None:
    bundle = tmp_path / "inventory"
    _inventory_bundle(bundle)
    inventory = bundle / "FORECASTER_INVENTORY.json"
    inventory.write_text(inventory.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(VerificationError, match="mismatch"):
        verify_inventory_bundle(bundle)


def test_sha_verification_rejects_unhashed_artifact(tmp_path: Path) -> None:
    bundle = tmp_path / "inventory"
    _inventory_bundle(bundle)
    (bundle / "unexpected.txt").write_text("not hashed\n", encoding="utf-8")

    with pytest.raises(VerificationError, match="coverage mismatch"):
        verify_sha256sums(bundle)
