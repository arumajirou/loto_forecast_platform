from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

from loto.statsforecast.runtime_lane_admission import (
    inspect_target_host_archive,
    render_admission_markdown,
    write_admission_artifacts,
)

_COMMIT = "c" * 40


def _write_json(bundle: zipfile.ZipFile, name: str, payload) -> None:
    bundle.writestr(name, json.dumps(payload, sort_keys=True))


def _archive(tmp_path: Path, *, model_status: str = "VERIFIED") -> Path:
    archive = tmp_path / "result.zip"
    prefix = "statsforecast-target-test"
    model_names = ("Naive", "NaNModel")
    rows = [
        {
            "model_name": "Naive",
            "expected_status": "EXPECTED_PASS",
            "status": model_status,
            "lifecycle_status": "VERIFIED",
            "champion_eligible": True,
            "finite": True,
            "shape_ok": True,
            "identity_ok": True,
            "series_horizon_ok": True,
            "duplicate_keys": False,
        },
        {
            "model_name": "NaNModel",
            "expected_status": "EXPECTED_NEGATIVE_PASS",
            "status": "EXPECTED_NEGATIVE_PASS",
            "lifecycle_status": "EXPECTED_NOT_APPLICABLE",
            "champion_eligible": False,
            "finite": False,
            "shape_ok": True,
            "identity_ok": True,
            "series_horizon_ok": True,
            "duplicate_keys": False,
        },
    ]
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    with zipfile.ZipFile(archive, "w") as bundle:
        _write_json(
            bundle,
            f"{prefix}/TARGET_HOST_PREFLIGHT.json",
            {
                "status": "PASS",
                "python": {"is_python_3_13": True},
                "working_tree_clean": True,
                "git_head": {"stdout": _COMMIT},
            },
        )
        _write_json(
            bundle,
            f"{prefix}/TARGET_HOST_REPORT.json",
            {
                "status": "PASS",
                "preflight_status": "PASS",
                "error": None,
                "wheelhouse": None,
                "wheelhouse_verification": None,
                "horizon": 1,
                "seed": 1,
                "holdout_opened": False,
                "prospective_actual_known": False,
            },
        )
        base = f"{prefix}/runtime-runs/runtime"
        _write_json(
            bundle,
            f"{base}/RUNTIME_LANE_REPORT.json",
            {
                "status": "PASS",
                "target_package": "statsforecast",
                "target_version": "2.1.1",
                "python_lane": "3.13",
                "lock_returncode": 0,
                "sync_returncode": 0,
                "certification_returncode": 0,
                "inner_run": "/tmp/inner",
                "inner_checksum_verification": {"status": "PASS"},
                "holdout_opened": False,
                "prospective_actual_known": False,
            },
        )
        cert = f"{base}/certification/inner"
        _write_json(
            bundle,
            f"{cert}/VERIFICATION_REPORT.json",
            {
                "status": "VERIFIED",
                "formal_pass": True,
                "package_status": "VERIFIED",
                "inventory_status": "VERIFIED",
                "selected_all_models": True,
                "selected_model_count": 2,
                "executed_model_count": 2,
                "status_counts": counts,
                "lifecycle_requested": True,
                "holdout_opened": False,
                "prospective_actual_known": False,
                "accuracy_improvement_claimed": False,
            },
        )
        _write_json(bundle, f"{cert}/MODEL_RUNTIME_MATRIX.json", rows)
        _write_json(
            bundle,
            f"{cert}/PACKAGE_EVIDENCE.json",
            {
                "status": "VERIFIED",
                "installed_version": "2.1.1",
                "files": [
                    {
                        "path": "statsforecast/__init__.py",
                        "size_bytes": 10,
                        "sha256": "0" * 64,
                    }
                ],
            },
        )
        _write_json(
            bundle,
            f"{cert}/RUNTIME_INVENTORY.json",
            {
                "status": "VERIFIED",
                "complete": True,
                "pinned_count": 2,
                "runtime_export_count": 2,
                "runtime_exports": list(model_names),
                "available_count": 2,
                "missing": [],
                "extra": [],
            },
        )
        _write_json(
            bundle,
            f"{cert}/CONFIG.json",
            {
                "selected_models": list(model_names),
                "horizon": 1,
                "seed": 1,
                "n_jobs": 1,
                "actual_known": False,
                "lifecycle": True,
            },
        )
    return archive


def _package_pass(_archive: Path) -> dict:
    return {"status": "PASS", "failures": [], "archive_sha256": "a" * 64}


def _inspect(archive: Path) -> dict:
    return inspect_target_host_archive(
        archive,
        package_verifier=_package_pass,
        expected_model_names=("Naive", "NaNModel"),
        expected_negative_model_names=("NaNModel",),
        expected_commit=_COMMIT,
    )


def test_admits_consistent_formal_runtime_package(tmp_path: Path) -> None:
    report = _inspect(_archive(tmp_path))
    assert report["status"] == "ADMITTED"
    assert report["decision"] == "RUNTIME_CERTIFIED"
    assert report["formal_pass"] is True
    assert report["status_counts"] == {
        "EXPECTED_NEGATIVE_PASS": 1,
        "VERIFIED": 1,
    }
    assert "Failures" in render_admission_markdown(report)


def test_rejects_model_failure_even_when_outer_reports_claim_pass(tmp_path: Path) -> None:
    report = _inspect(_archive(tmp_path, model_status="EXECUTION_FAILED"))
    assert report["status"] == "REJECTED"
    assert report["decision"] == "MERGE_BLOCKED"
    assert any("model Naive status" in failure for failure in report["failures"])


def test_rejects_outer_package_verification_failure(tmp_path: Path) -> None:
    report = inspect_target_host_archive(
        _archive(tmp_path),
        package_verifier=lambda _path: {
            "status": "FAILED",
            "failures": ["archive SHA-256 mismatch"],
        },
        expected_model_names=("Naive", "NaNModel"),
        expected_negative_model_names=("NaNModel",),
        expected_commit=_COMMIT,
    )
    assert report["status"] == "REJECTED"
    assert any("outer package" in failure for failure in report["failures"])


def test_rejects_ambiguous_duplicate_verification_report(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as bundle:
        _write_json(bundle, "duplicate/VERIFICATION_REPORT.json", {})
    report = _inspect(archive)
    assert report["status"] == "REJECTED"
    assert any("exactly one" in failure for failure in report["failures"])


def test_rejects_archive_with_wrong_seed(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    rewritten = tmp_path / "wrong-seed.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(rewritten, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.endswith("/CONFIG.json"):
                config = json.loads(payload)
                config["seed"] = 7
                payload = json.dumps(config).encode()
            target.writestr(info.filename, payload)
    report = _inspect(rewritten)
    assert report["status"] == "REJECTED"
    assert any("config seed" in failure for failure in report["failures"])


def test_rejects_missing_expected_commit(tmp_path: Path) -> None:
    report = inspect_target_host_archive(
        _archive(tmp_path),
        package_verifier=_package_pass,
        expected_model_names=("Naive", "NaNModel"),
        expected_negative_model_names=("NaNModel",),
    )
    assert report["status"] == "REJECTED"
    assert any("expected Git commit" in failure for failure in report["failures"])


def test_rejects_symlink_member_type(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as bundle:
        info = zipfile.ZipInfo("statsforecast-target-test/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, "TARGET_HOST_REPORT.json")
    report = _inspect(archive)
    assert report["status"] == "REJECTED"
    assert any("not a regular file" in failure for failure in report["failures"])


def test_writes_admission_artifacts_with_checksums(tmp_path: Path) -> None:
    report = _inspect(_archive(tmp_path))
    paths = write_admission_artifacts(report, tmp_path / "admission")
    assert paths["json"].is_file()
    assert paths["markdown"].is_file()
    rows = paths["sha256sums"].read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert all("  ADMISSION_REPORT" in row for row in rows)
