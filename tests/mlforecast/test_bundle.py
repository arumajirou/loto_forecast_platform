from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from loto.mlforecast.artifacts import _write_manifest
from loto.mlforecast.bundle import bundle_run, verify_run_directory


def _write_report(run_dir: Path, status: str) -> None:
    payload = {"run_id": run_dir.name, "status": status}
    (run_dir / "RUNTIME_CERTIFICATION.json").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )


def _make_run(tmp_path: Path, *, status: str = "FAILED") -> Path:
    run_dir = tmp_path / "mlforecast-runtime-20260805-000000-000001"
    run_dir.mkdir()
    _write_report(run_dir, status)
    (run_dir / "failure.txt").write_text("evidence\n", encoding="utf-8")
    if status == "RUNTIME_CERTIFIED":
        inputs = run_dir / "inputs"
        inputs.mkdir()
        (inputs / "mlforecast-1.1.0-py3-none-any.whl").write_bytes(b"wheel")
        (run_dir / "core_ridge_predictions.csv").write_text(
            "x\n1\n",
            encoding="utf-8",
        )
        (run_dir / "auto_ridge_predictions.csv").write_text(
            "x\n1\n",
            encoding="utf-8",
        )
        (run_dir / "auto_ridge_trials.csv").write_text(
            "x\n1\n",
            encoding="utf-8",
        )
        core_model = run_dir / "models" / "core-ridge"
        auto_model = run_dir / "models" / "auto-ridge"
        core_model.mkdir(parents=True)
        auto_model.mkdir(parents=True)
        (core_model / "model.pkl").write_bytes(b"core")
        (auto_model / "model.pkl").write_bytes(b"auto")
    _write_manifest(run_dir)
    return run_dir


def test_bundle_failed_run_is_sorted_and_hashed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    result = bundle_run(run_dir, tmp_path / "bundles")
    assert result.source_status == "FAILED"
    assert result.sha256_path.read_text(encoding="utf-8").split()[0] == result.sha256
    with zipfile.ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert f"{run_dir.name}/BUNDLE_VERIFICATION.json" in names
        assert all(
            info.date_time == (1980, 1, 1, 0, 0, 0)
            for info in archive.infolist()
        )


def test_bundle_bytes_are_deterministic(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    first = bundle_run(run_dir, tmp_path / "first")
    second = bundle_run(run_dir, tmp_path / "second")
    assert first.sha256 == second.sha256
    assert first.zip_path.read_bytes() == second.zip_path.read_bytes()


def test_verify_run_rejects_tampered_artifact(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    (run_dir / "failure.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="manifest verification failed"):
        verify_run_directory(run_dir)


def test_certified_run_requires_model_and_prediction_artifacts(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "mlforecast-runtime-20260805-000000-000001"
    run_dir.mkdir()
    _write_report(run_dir, "RUNTIME_CERTIFIED")
    _write_manifest(run_dir)
    with pytest.raises(RuntimeError, match="missing required artifacts"):
        verify_run_directory(run_dir)
