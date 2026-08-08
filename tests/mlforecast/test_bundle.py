from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from loto.mlforecast.artifacts import _write_manifest
from loto.mlforecast.bundle import (
    bundle_run,
    verify_bundle_archive,
    verify_run_directory,
)


def _write_report(run_dir: Path, status: str) -> None:
    payload = {"run_id": run_dir.name, "status": status}
    (run_dir / "RUNTIME_CERTIFICATION.json").write_text(
        json.dumps(payload) + "\n", encoding="utf-8"
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
        for name in (
            "core_ridge_predictions.csv",
            "auto_ridge_predictions.csv",
            "auto_ridge_trials.csv",
        ):
            (run_dir / name).write_text("x\n1\n", encoding="utf-8")
        core_model = run_dir / "models" / "core-ridge"
        auto_model = run_dir / "models" / "auto-ridge"
        core_model.mkdir(parents=True)
        auto_model.mkdir(parents=True)
        (core_model / "model.pkl").write_bytes(b"core")
        (auto_model / "model.pkl").write_bytes(b"auto")
    _write_manifest(run_dir)
    return run_dir


def test_bundle_failed_run_is_sorted_hashed_and_independently_verified(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(tmp_path)
    result = bundle_run(run_dir, tmp_path / "bundles")
    assert result.source_status == "FAILED"
    assert result.sha256_path.read_text(encoding="utf-8").split()[0] == result.sha256
    verified = verify_bundle_archive(result.zip_path, result.sha256_path)
    assert verified.run_id == run_dir.name
    assert verified.source_status == "FAILED"
    with zipfile.ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert f"{run_dir.name}/BUNDLE_VERIFICATION.json" in names
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())


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


def test_certified_run_requires_model_and_prediction_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "mlforecast-runtime-20260805-000000-000001"
    run_dir.mkdir()
    _write_report(run_dir, "RUNTIME_CERTIFIED")
    _write_manifest(run_dir)
    with pytest.raises(RuntimeError, match="missing required artifacts"):
        verify_run_directory(run_dir)


def test_verify_run_rejects_symlink_root(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    link = tmp_path / "mlforecast-runtime-20260805-000000-000002"
    link.symlink_to(run_dir, target_is_directory=True)
    with pytest.raises(RuntimeError, match="must not be a symlink"):
        verify_run_directory(link)


def test_verify_run_rejects_parent_symlink_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "mlforecast-runtime-20260805-000000-000001"
    run_dir.mkdir()
    _write_report(run_dir, "FAILED")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.txt").write_text("evidence\n", encoding="utf-8")
    (run_dir / "linked").symlink_to(outside, target_is_directory=True)
    manifest = {
        "artifacts": [
            {
                "path": "RUNTIME_CERTIFICATION.json",
                "size_bytes": (run_dir / "RUNTIME_CERTIFICATION.json").stat().st_size,
                "sha256": __import__("hashlib")
                .sha256((run_dir / "RUNTIME_CERTIFICATION.json").read_bytes())
                .hexdigest(),
            },
            {
                "path": "linked/evidence.txt",
                "size_bytes": len(b"evidence\n"),
                "sha256": __import__("hashlib").sha256(b"evidence\n").hexdigest(),
            },
        ]
    }
    (run_dir / "ARTIFACT_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "SHA256SUMS").write_text(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in manifest["artifacts"]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="contains a symlink"):
        verify_run_directory(run_dir)


def test_bundle_rejects_output_inside_source_run(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    with pytest.raises(RuntimeError, match="must not be inside"):
        bundle_run(run_dir, run_dir / "bundles")


def test_verify_bundle_rejects_wrong_sidecar(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    result = bundle_run(run_dir, tmp_path / "bundles")
    result.sha256_path.write_text(f"{'0' * 64}  {result.zip_path.name}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify_bundle_archive(result.zip_path, result.sha256_path)


def test_verify_bundle_rejects_zip_slip_entry(tmp_path: Path) -> None:
    archive_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../evil.txt", b"bad")
    with pytest.raises(RuntimeError, match="unsafe artifact path"):
        verify_bundle_archive(archive_path)


def test_verify_bundle_rejects_symlink_entry(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo(
        "mlforecast-runtime-20260805-000000-000001/link",
        date_time=(1980, 1, 1, 0, 0, 0),
    )
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"target")
    with pytest.raises(RuntimeError, match="non-regular entry"):
        verify_bundle_archive(archive_path)


def test_verify_bundle_writes_external_report(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    result = bundle_run(run_dir, tmp_path / "bundles")
    report = tmp_path / "verification.json"
    verified = verify_bundle_archive(result.zip_path, result.sha256_path, report_path=report)
    assert verified.report_path == report.absolute()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "BUNDLE_VERIFIED"
    assert payload["run_id"] == run_dir.name


def test_verify_bundle_rejects_file_count_limit(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    result = bundle_run(run_dir, tmp_path / "bundles")
    with pytest.raises(RuntimeError, match="entry count"):
        verify_bundle_archive(result.zip_path, max_files=1)


def test_verify_run_rejects_symlink_created_after_manifest(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("symlink privileges vary on Windows")
    run_dir = _make_run(tmp_path)
    target = run_dir / "failure.txt"
    target.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_text("evidence\n", encoding="utf-8")
    target.symlink_to(outside)
    with pytest.raises(RuntimeError, match="contains a symlink"):
        verify_run_directory(run_dir)
