from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from loto.reconciliation import package_verifier as verifier


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, verifier._FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = verifier._REGULAR_FILE_MODE << 16
    return info


def _build(tmp_path: Path, *, status: str = "VERIFIED") -> tuple[Path, Path, str]:
    run_id = "hierarchicalforecast-runtime-test-1"
    runtime = _canonical({"run_id": run_id, "status": status, "run_directory": f"/x/{run_id}"})
    methods = _canonical({"results": []})
    inputs = _canonical({"games": {}})
    first = {
        "RUNTIME_CERTIFICATION.json": runtime,
        "METHOD_RESULTS.json": methods,
        "INPUT_EVIDENCE.json": inputs,
    }
    artifact_rows = [
        {"path": name, "bytes": len(data), "sha256": _sha(data)} for name, data in first.items()
    ]
    artifact = _canonical({"run_id": run_id, "files": artifact_rows})
    primary = {**first, "ARTIFACT_MANIFEST.json": artifact}
    sums = "".join(f"{_sha(data)}  {name}\n" for name, data in primary.items()).encode()
    required = {**primary, "SHA256SUMS": sums}
    package_rows = [
        {"path": name, "bytes": len(data), "sha256": _sha(data)} for name, data in required.items()
    ]
    package = _canonical(
        {
            "run_id": run_id,
            "certification_status": status,
            "files": package_rows,
            "content_set_sha256": _sha(_canonical(package_rows)),
        }
    )
    zip_path = tmp_path / f"{run_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, data in required.items():
            archive.writestr(_info(f"{run_id}/{name}"), data)
        archive.writestr(_info(f"{run_id}/{verifier.PACKAGE_MANIFEST}"), package)
    sidecar = Path(f"{zip_path}.sha256")
    sidecar.write_text(f"{verifier._sha256_file(zip_path)}  {zip_path.name}\n")
    return zip_path, sidecar, run_id


def _rewrite(zip_path: Path, mutate) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        rows = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(zip_path, "w") as archive:
        for info, data in rows:
            name, changed = mutate(info.filename, data)
            archive.writestr(_info(name), changed)
    Path(f"{zip_path}.sha256").write_text(f"{verifier._sha256_file(zip_path)}  {zip_path.name}\n")


def test_verify_package_and_cli_success(tmp_path: Path, capsys) -> None:
    zip_path, sidecar, run_id = _build(tmp_path)
    report = verifier.verify_package(zip_path)
    assert report["status"] == "VERIFIED"
    assert report["run_id"] == run_id
    assert report["zip_sidecar"] == str(sidecar)
    assert verifier.main(["--zip", str(zip_path)]) == 0
    assert json.loads(capsys.readouterr().out)["formal_success"] is True


def test_sidecar_mismatch_returns_two(tmp_path: Path, capsys) -> None:
    zip_path, sidecar, _ = _build(tmp_path)
    sidecar.write_text("wrong\n")
    assert verifier.main(["--zip", str(zip_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED_PACKAGE_VERIFICATION"


def test_noncanonical_package_manifest_is_rejected(tmp_path: Path) -> None:
    zip_path, _, _ = _build(tmp_path)

    def mutate(name, data):
        if name.endswith(verifier.PACKAGE_MANIFEST):
            return name, json.dumps(json.loads(data), separators=(",", ":")).encode()
        return name, data

    _rewrite(zip_path, mutate)
    with pytest.raises(verifier.PackageVerificationError, match="not canonical"):
        verifier.verify_package(zip_path)


def test_package_member_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    zip_path, _, _ = _build(tmp_path)

    def mutate(name, data):
        if name.endswith("METHOD_RESULTS.json"):
            return name, b'{"results":[1]}\n'
        return name, data

    _rewrite(zip_path, mutate)
    with pytest.raises(verifier.PackageVerificationError, match="PACKAGE_MANIFEST evidence"):
        verifier.verify_package(zip_path)


def test_internal_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    zip_path, _, _ = _build(tmp_path)

    def mutate(name, data):
        if name.endswith("SHA256SUMS"):
            return name, data.replace(data[:64], b"0" * 64, 1)
        if name.endswith(verifier.PACKAGE_MANIFEST):
            payload = json.loads(data)
            for row in payload["files"]:
                if row["path"] == "SHA256SUMS":
                    broken = next(
                        original for member, original in members if member.endswith("SHA256SUMS")
                    )
                    changed = broken.replace(broken[:64], b"0" * 64, 1)
                    row["bytes"] = len(changed)
                    row["sha256"] = _sha(changed)
            payload["content_set_sha256"] = _sha(_canonical(payload["files"]))
            return name, _canonical(payload)
        return name, data

    with zipfile.ZipFile(zip_path) as archive:
        members = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    _rewrite(zip_path, mutate)
    with pytest.raises(verifier.PackageVerificationError, match="internal SHA256SUMS"):
        verifier.verify_package(zip_path)


def test_runtime_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    zip_path, _, _ = _build(tmp_path)

    with zipfile.ZipFile(zip_path) as archive:
        rows = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    mapping = dict(rows)
    runtime_name = next(name for name in mapping if name.endswith("RUNTIME_CERTIFICATION.json"))
    runtime = json.loads(mapping[runtime_name])
    runtime["status"] = "FAILED_RUNTIME"
    mapping[runtime_name] = _canonical(runtime)
    artifact_name = next(name for name in mapping if name.endswith("ARTIFACT_MANIFEST.json"))
    artifact = json.loads(mapping[artifact_name])
    for row in artifact["files"]:
        member_name = next(name for name in mapping if name.endswith(row["path"]))
        row["bytes"] = len(mapping[member_name])
        row["sha256"] = _sha(mapping[member_name])
    mapping[artifact_name] = _canonical(artifact)
    sums_name = next(name for name in mapping if name.endswith("SHA256SUMS"))
    primary_names = [name for name in mapping if Path(name).name in verifier.PRIMARY_ARTIFACTS]
    mapping[sums_name] = "".join(
        f"{_sha(mapping[name])}  {Path(name).name}\n" for name in primary_names
    ).encode()
    manifest_name = next(name for name in mapping if name.endswith(verifier.PACKAGE_MANIFEST))
    manifest = json.loads(mapping[manifest_name])
    for row in manifest["files"]:
        member_name = next(name for name in mapping if Path(name).name == row["path"])
        row["bytes"] = len(mapping[member_name])
        row["sha256"] = _sha(mapping[member_name])
    manifest["content_set_sha256"] = _sha(_canonical(manifest["files"]))
    mapping[manifest_name] = _canonical(manifest)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, data in mapping.items():
            archive.writestr(_info(name), data)
    Path(f"{zip_path}.sha256").write_text(f"{verifier._sha256_file(zip_path)}  {zip_path.name}\n")
    with pytest.raises(verifier.PackageVerificationError, match="identity/status"):
        verifier.verify_package(zip_path)


def test_unsafe_member_is_rejected(tmp_path: Path) -> None:
    zip_path, _, _ = _build(tmp_path)
    with zipfile.ZipFile(zip_path) as archive:
        rows = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, data in rows:
            archive.writestr(_info(name), data)
        archive.writestr(_info("../escape"), b"x")
    Path(f"{zip_path}.sha256").write_text(f"{verifier._sha256_file(zip_path)}  {zip_path.name}\n")
    with pytest.raises(verifier.PackageVerificationError, match="coverage"):
        verifier.verify_package(zip_path)
