from __future__ import annotations

import json
import zipfile
from pathlib import Path

from loto.statsforecast.runtime_lane_admission_hardening import (
    inspect_target_host_archive,
)


def _rows() -> list[dict]:
    return [
        {
            "model_name": "Naive",
            "forecast_mode": "point",
            "requested_levels": [],
            "device": "cpu",
            "device_type": "cpu",
            "gpu_not_applicable": True,
            "gpu_pid": None,
            "vram_mb": None,
            "cpu_fallback": False,
            "n_jobs": 1,
        }
    ]


def _archive(tmp_path: Path, rows: list[dict] | None = None) -> Path:
    archive = tmp_path / "result.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "target/runtime/MODEL_RUNTIME_MATRIX.json",
            json.dumps(_rows() if rows is None else rows),
        )
    return archive


def _pass(_archive: Path, **_kwargs) -> dict:
    return {
        "status": "ADMITTED",
        "decision": "RUNTIME_CERTIFIED",
        "formal_pass": True,
        "failures": [],
    }


def test_accepts_hardened_point_cpu_evidence(tmp_path: Path) -> None:
    report = inspect_target_host_archive(_archive(tmp_path), base_inspector=_pass)
    assert report["formal_pass"] is True
    assert report["point_cpu_hardening_checked"] is True


def test_rejects_interval_mode(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["forecast_mode"] = "interval"
    report = inspect_target_host_archive(
        _archive(tmp_path, rows), base_inspector=_pass
    )
    assert report["decision"] == "MERGE_BLOCKED"
    assert any("forecast_mode" in item for item in report["failures"])


def test_rejects_non_cpu_device(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["device"] = "cuda"
    report = inspect_target_host_archive(
        _archive(tmp_path, rows), base_inspector=_pass
    )
    assert report["formal_pass"] is False
    assert any("device" in item for item in report["failures"])


def test_rejects_missing_matrix(tmp_path: Path) -> None:
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w"):
        pass
    report = inspect_target_host_archive(archive, base_inspector=_pass)
    assert report["formal_pass"] is False
    assert any("hardened point-certificate evidence" in item for item in report["failures"])


def test_preserves_base_gate_failures(tmp_path: Path) -> None:
    def reject(_archive: Path, **_kwargs) -> dict:
        return {
            "status": "REJECTED",
            "decision": "MERGE_BLOCKED",
            "formal_pass": False,
            "failures": ["outer SHA mismatch"],
        }

    report = inspect_target_host_archive(
        _archive(tmp_path), base_inspector=reject
    )
    assert report["formal_pass"] is False
    assert "outer SHA mismatch" in report["failures"]
