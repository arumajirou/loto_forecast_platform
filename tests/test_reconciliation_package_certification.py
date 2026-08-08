from __future__ import annotations

import errno
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from loto.reconciliation import portable_package_certification as pc


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_run(
    tmp_path: Path,
    *,
    status: str = "VERIFIED",
    name: str = "hierarchicalforecast-runtime-test-1",
) -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir()
    certification = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "status": status,
        "run_directory": str(run_dir),
    }
    (run_dir / "RUNTIME_CERTIFICATION.json").write_text(
        json.dumps(certification, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "METHOD_RESULTS.json").write_text('{"results": []}\n', encoding="utf-8")
    (run_dir / "INPUT_EVIDENCE.json").write_text('{"games": {}}\n', encoding="utf-8")
    rows = []
    for filename in pc.PRIMARY_ARTIFACTS[:3]:
        path = run_dir / filename
        rows.append({"path": filename, "bytes": path.stat().st_size, "sha256": _sha(path)})
    (run_dir / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps({"schema_version": 1, "run_id": run_dir.name, "files": rows}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    checksums = "".join(
        f"{_sha(run_dir / filename)}  {filename}\n" for filename in pc.PRIMARY_ARTIFACTS
    )
    (run_dir / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return run_dir


def test_package_run_creates_verified_zip_and_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _make_run(tmp_path)

    def unsupported_link(_source, _destination):
        raise OSError(errno.EPERM, "hard links unavailable")

    monkeypatch.setattr(pc.os, "link", unsupported_link)
    result = pc.package_run(run_dir, certification_status="VERIFIED")

    zip_path = Path(result["path"])
    sidecar = Path(result["sha256_sidecar"])
    assert result["status"] == "VERIFIED"
    assert result["member_count"] == 6
    assert result["reused_existing"] is False
    assert result["publication_method"] == "exclusive_copy"
    assert result["sha256"] == _sha(zip_path)
    assert sidecar.read_text(encoding="utf-8") == f"{_sha(zip_path)}  {zip_path.name}\n"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert names == {
            *(f"{run_dir.name}/{name}" for name in pc.REQUIRED_ARTIFACTS),
            f"{run_dir.name}/{pc.PACKAGE_MANIFEST}",
        }
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == pc._FIXED_ZIP_TIMESTAMP
            assert (info.external_attr >> 16) & 0xFFFF == pc._REGULAR_FILE_MODE
        manifest = json.loads(archive.read(f"{run_dir.name}/{pc.PACKAGE_MANIFEST}").decode("utf-8"))
        assert manifest["run_id"] == run_dir.name
        assert manifest["certification_status"] == "VERIFIED"
        assert len(manifest["files"]) == 5


def test_package_zip_is_reused_without_overwrite_for_unchanged_evidence(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)

    first = pc.package_run(run_dir, certification_status="VERIFIED")
    first_bytes = Path(first["path"]).read_bytes()
    second = pc.package_run(run_dir, certification_status="VERIFIED")

    assert Path(second["path"]).read_bytes() == first_bytes
    assert second["sha256"] == first["sha256"]
    assert first["reused_existing"] is False
    assert second["reused_existing"] is True
    assert second["publication_method"] == "reused_existing"


def test_existing_different_zip_is_rejected_without_overwrite(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    first = pc.package_run(run_dir, certification_status="VERIFIED")
    zip_path = Path(first["path"])
    sidecar = Path(first["sha256_sidecar"])
    zip_path.write_bytes(b"tampered-existing-zip")
    sidecar_before = sidecar.read_bytes()

    with pytest.raises(pc.PackageIntegrityError, match="existing ZIP differs"):
        pc.package_run(run_dir, certification_status="VERIFIED")

    assert zip_path.read_bytes() == b"tampered-existing-zip"
    assert sidecar.read_bytes() == sidecar_before


def test_existing_sidecar_mismatch_is_not_overwritten(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    first = pc.package_run(run_dir, certification_status="VERIFIED")
    sidecar = Path(first["sha256_sidecar"])
    sidecar.write_text("wrong sidecar\n", encoding="utf-8")

    with pytest.raises(pc.PackageIntegrityError, match="existing ZIP sidecar"):
        pc.package_run(run_dir, certification_status="VERIFIED")

    assert sidecar.read_text(encoding="utf-8") == "wrong sidecar\n"


def test_verification_failure_and_partial_copy_publish_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_run = _make_run(tmp_path, name="hierarchicalforecast-runtime-test-preverify")

    def reject_zip(_zip_path, *, package_manifest):
        raise pc.PackageIntegrityError(f"rejected {package_manifest['run_id']}")

    original_verify = pc._verify_zip
    monkeypatch.setattr(pc, "_verify_zip", reject_zip)
    with pytest.raises(pc.PackageIntegrityError, match="rejected"):
        pc.package_run(first_run, certification_status="VERIFIED")
    assert not first_run.with_suffix(".zip").exists()
    assert not Path(f"{first_run.with_suffix('.zip')}.sha256").exists()

    monkeypatch.setattr(pc, "_verify_zip", original_verify)
    second_run = _make_run(tmp_path, name="hierarchicalforecast-runtime-test-copy")
    monkeypatch.setattr(
        pc.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EPERM, "unsupported")),
    )

    def fail_copy(source, destination):
        destination.write(source.read(16))
        raise OSError("simulated copy failure")

    monkeypatch.setattr(pc, "_copy_stream", fail_copy)
    with pytest.raises(pc.PackageIntegrityError, match="cannot publish immutable ZIP by copy"):
        pc.package_run(second_run, certification_status="VERIFIED")
    assert not second_run.with_suffix(".zip").exists()
    assert not Path(f"{second_run.with_suffix('.zip')}.sha256").exists()


def test_corrupted_artifact_is_rejected_before_zip_creation(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    (run_dir / "METHOD_RESULTS.json").write_text("corrupted\n", encoding="utf-8")

    with pytest.raises(pc.PackageIntegrityError, match="SHA256SUMS verification failed"):
        pc.package_run(run_dir, certification_status="VERIFIED")

    assert not run_dir.with_suffix(".zip").exists()


def test_unsafe_checksum_filename_is_rejected(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    with (run_dir / "SHA256SUMS").open("a", encoding="utf-8") as stream:
        stream.write(f"{'0' * 64}  ../escape\n")

    with pytest.raises(pc.PackageIntegrityError, match="unsafe artifact path"):
        pc.package_run(run_dir, certification_status="VERIFIED")


def test_blocked_certification_is_packaged_but_main_returns_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _make_run(tmp_path, status="BLOCKED_DEPENDENCY")
    monkeypatch.setattr(
        pc.runtime,
        "run_certification",
        lambda config: {
            "status": "BLOCKED_DEPENDENCY",
            "run_directory": str(run_dir),
        },
    )

    exit_code = pc.main(["--output-root", str(tmp_path), "--games", "loto7"])

    assert exit_code == 2
    assert run_dir.with_suffix(".zip").is_file()
    assert Path(f"{run_dir.with_suffix('.zip')}.sha256").is_file()


def test_packaging_failure_returns_three_and_preserves_run_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing-run"
    monkeypatch.setattr(
        pc.runtime,
        "run_certification",
        lambda config: {
            "run_id": missing.name,
            "status": "VERIFIED",
            "run_directory": str(missing),
        },
    )

    assert pc.main(["--output-root", str(tmp_path)]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAILED_PACKAGING"
    assert payload["phase"] == "package"
    assert payload["run_id"] == missing.name
    assert payload["run_directory"] == str(missing)
    assert payload["certification_status"] == "VERIFIED"


def test_certification_harness_failure_is_distinct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(_config):
        raise RuntimeError("runtime harness crashed")

    monkeypatch.setattr(pc.runtime, "run_certification", fail)

    assert pc.main(["--output-root", str(tmp_path)]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAILED_CERTIFICATION_HARNESS"
    assert payload["phase"] == "certification"
    assert "runtime harness crashed" in payload["error"]


def test_invalid_configuration_returns_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_config(**_kwargs):
        raise ValueError("invalid formal configuration")

    monkeypatch.setattr(pc.runtime, "RuntimeCertificationConfig", reject_config)

    assert pc.main(["--output-root", str(tmp_path)]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "INVALID_CONFIGURATION"
    assert payload["phase"] == "configuration"
    assert "invalid formal configuration" in payload["error"]
