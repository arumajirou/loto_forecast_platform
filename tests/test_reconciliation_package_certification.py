from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from loto.reconciliation import package_certification as pc


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_run(tmp_path: Path, *, status: str = "VERIFIED") -> Path:
    run_dir = tmp_path / "hierarchicalforecast-runtime-test-1"
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


def test_package_run_creates_verified_zip_and_sidecar(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)

    result = pc.package_run(run_dir, certification_status="VERIFIED")

    zip_path = Path(result["path"])
    sidecar = Path(result["sha256_sidecar"])
    assert result["status"] == "VERIFIED"
    assert result["member_count"] == 6
    assert result["sha256"] == _sha(zip_path)
    assert sidecar.read_text(encoding="utf-8") == f"{_sha(zip_path)}  {zip_path.name}\n"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert names == {
            *(f"{run_dir.name}/{name}" for name in pc.REQUIRED_ARTIFACTS),
            f"{run_dir.name}/{pc.PACKAGE_MANIFEST}",
        }
        manifest = json.loads(
            archive.read(f"{run_dir.name}/{pc.PACKAGE_MANIFEST}").decode("utf-8")
        )
        assert manifest["run_id"] == run_dir.name
        assert manifest["certification_status"] == "VERIFIED"
        assert len(manifest["files"]) == 5


def test_package_zip_is_deterministic_for_unchanged_evidence(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)

    first = pc.package_run(run_dir, certification_status="VERIFIED")
    first_bytes = Path(first["path"]).read_bytes()
    second = pc.package_run(run_dir, certification_status="VERIFIED")

    assert Path(second["path"]).read_bytes() == first_bytes
    assert second["sha256"] == first["sha256"]


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


def test_packaging_failure_returns_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing-run"
    monkeypatch.setattr(
        pc.runtime,
        "run_certification",
        lambda config: {"status": "VERIFIED", "run_directory": str(missing)},
    )

    assert pc.main(["--output-root", str(tmp_path)]) == 3
