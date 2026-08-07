"""Verify an existing HierarchicalForecast evidence ZIP without rerunning certification."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

PRIMARY_ARTIFACTS = (
    "RUNTIME_CERTIFICATION.json",
    "METHOD_RESULTS.json",
    "INPUT_EVIDENCE.json",
    "ARTIFACT_MANIFEST.json",
)
REQUIRED_ARTIFACTS = (*PRIMARY_ARTIFACTS, "SHA256SUMS")
PACKAGE_MANIFEST = "PACKAGE_MANIFEST.json"
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_REGULAR_FILE_MODE = 0o100644


class PackageVerificationError(RuntimeError):
    """Raised when a transferred package fails independent verification."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _safe_name(value: str) -> str:
    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or candidate.name != value
        or ".." in candidate.parts
        or "\\" in value
    ):
        raise PackageVerificationError(f"unsafe artifact name: {value!r}")
    return value


def _require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PackageVerificationError(f"{label} is not a regular file: {path}")
    return path


def _load_json_bytes(name: str, data: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageVerificationError(f"invalid JSON member {name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackageVerificationError(f"JSON member root must be an object: {name}")
    return payload


def _parse_internal_checksums(data: bytes) -> dict[str, str]:
    try:
        rows = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise PackageVerificationError("SHA256SUMS is not valid UTF-8") from exc
    parsed: dict[str, str] = {}
    for row in rows:
        if not row.strip():
            continue
        try:
            digest, name = row.split("  ", 1)
        except ValueError as exc:
            raise PackageVerificationError(f"invalid SHA256SUMS row: {row!r}") from exc
        name = _safe_name(name)
        if not _valid_sha256(digest):
            raise PackageVerificationError(f"invalid SHA-256 for {name}")
        if name in parsed:
            raise PackageVerificationError(f"duplicate SHA256SUMS entry: {name}")
        parsed[name] = digest
    if set(parsed) != set(PRIMARY_ARTIFACTS):
        raise PackageVerificationError("SHA256SUMS coverage mismatch")
    return parsed


def _verify_member_metadata(info: zipfile.ZipInfo, run_id: str) -> None:
    path = PurePosixPath(info.filename)
    mode = (info.external_attr >> 16) & 0xFFFF
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) != 2
        or path.parts[0] != run_id
        or info.is_dir()
        or info.flag_bits & 1
        or info.date_time != _FIXED_ZIP_TIMESTAMP
        or info.compress_type != zipfile.ZIP_STORED
        or info.create_system != 3
        or mode != _REGULAR_FILE_MODE
    ):
        raise PackageVerificationError(f"invalid ZIP member metadata: {info.filename}")


def _derive_run_id(names: list[str]) -> str:
    manifests = [name for name in names if PurePosixPath(name).name == PACKAGE_MANIFEST]
    if len(manifests) != 1:
        raise PackageVerificationError("ZIP must contain exactly one package manifest")
    path = PurePosixPath(manifests[0])
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 2:
        raise PackageVerificationError("package manifest path is unsafe")
    return _safe_name(path.parts[0])


def _verify_artifact_manifest(
    payload: dict[str, Any],
    run_id: str,
    members: dict[str, bytes],
) -> None:
    if payload.get("run_id") != run_id:
        raise PackageVerificationError("ARTIFACT_MANIFEST run_id mismatch")
    rows = payload.get("files")
    if not isinstance(rows, list):
        raise PackageVerificationError("ARTIFACT_MANIFEST files must be a list")
    expected = set(PRIMARY_ARTIFACTS[:3])
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PackageVerificationError("invalid ARTIFACT_MANIFEST row")
        name = _safe_name(str(row.get("path", "")))
        if name in observed:
            raise PackageVerificationError(f"duplicate ARTIFACT_MANIFEST row: {name}")
        observed.add(name)
        data = members[name]
        if row.get("bytes") != len(data) or row.get("sha256") != _sha256_bytes(data):
            raise PackageVerificationError(f"ARTIFACT_MANIFEST evidence mismatch: {name}")
    if observed != expected:
        raise PackageVerificationError("ARTIFACT_MANIFEST coverage mismatch")


def verify_package(
    zip_path: Path,
    *,
    sidecar_path: Path | None = None,
    expected_status: str = "VERIFIED",
) -> dict[str, object]:
    """Independently verify a transferred ZIP, sidecar, and every internal integrity layer."""
    zip_path = _require_regular_file(zip_path, "ZIP")
    sidecar = sidecar_path or Path(f"{zip_path}.sha256")
    sidecar = _require_regular_file(sidecar, "ZIP sidecar")
    digest = _sha256_file(zip_path)
    expected_sidecar = f"{digest}  {zip_path.name}\n"
    try:
        observed_sidecar = sidecar.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PackageVerificationError(f"cannot read ZIP sidecar: {exc}") from exc
    if observed_sidecar != expected_sidecar:
        raise PackageVerificationError("ZIP sidecar mismatch")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise PackageVerificationError("ZIP contains duplicate member names")
            run_id = _derive_run_id(names)
            expected_names = {
                *(f"{run_id}/{name}" for name in REQUIRED_ARTIFACTS),
                f"{run_id}/{PACKAGE_MANIFEST}",
            }
            if set(names) != expected_names:
                raise PackageVerificationError("ZIP member coverage mismatch")
            for info in infos:
                _verify_member_metadata(info, run_id)
            if archive.testzip() is not None:
                raise PackageVerificationError("ZIP CRC verification failed")
            members = {
                name: archive.read(f"{run_id}/{name}") for name in REQUIRED_ARTIFACTS
            }
            manifest_bytes = archive.read(f"{run_id}/{PACKAGE_MANIFEST}")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise PackageVerificationError(f"cannot read ZIP: {exc}") from exc

    package_manifest = _load_json_bytes(PACKAGE_MANIFEST, manifest_bytes)
    if manifest_bytes != _canonical_json_bytes(package_manifest):
        raise PackageVerificationError("PACKAGE_MANIFEST is not canonical")
    if (
        package_manifest.get("run_id") != run_id
        or package_manifest.get("certification_status") != expected_status
    ):
        raise PackageVerificationError("package identity or certification status mismatch")
    rows = package_manifest.get("files")
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_ARTIFACTS):
        raise PackageVerificationError("PACKAGE_MANIFEST files must have exact coverage")
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PackageVerificationError("invalid PACKAGE_MANIFEST row")
        name = _safe_name(str(row.get("path", "")))
        if name in observed:
            raise PackageVerificationError(f"duplicate PACKAGE_MANIFEST row: {name}")
        observed.add(name)
        data = members[name]
        if row.get("bytes") != len(data) or row.get("sha256") != _sha256_bytes(data):
            raise PackageVerificationError(f"PACKAGE_MANIFEST evidence mismatch: {name}")
    if observed != set(REQUIRED_ARTIFACTS):
        raise PackageVerificationError("PACKAGE_MANIFEST coverage mismatch")
    content_set = _sha256_bytes(_canonical_json_bytes(rows))
    if package_manifest.get("content_set_sha256") != content_set:
        raise PackageVerificationError("package content-set SHA-256 mismatch")

    checksums = _parse_internal_checksums(members["SHA256SUMS"])
    for name, expected_digest in checksums.items():
        if _sha256_bytes(members[name]) != expected_digest:
            raise PackageVerificationError(f"internal SHA256SUMS mismatch: {name}")

    runtime = _load_json_bytes("RUNTIME_CERTIFICATION.json", members["RUNTIME_CERTIFICATION.json"])
    if runtime.get("run_id") != run_id or runtime.get("status") != expected_status:
        raise PackageVerificationError("runtime certification identity/status mismatch")
    recorded_directory = Path(str(runtime.get("run_directory", "")))
    if recorded_directory.name != run_id:
        raise PackageVerificationError("runtime run_directory does not identify the package")
    _load_json_bytes("METHOD_RESULTS.json", members["METHOD_RESULTS.json"])
    _load_json_bytes("INPUT_EVIDENCE.json", members["INPUT_EVIDENCE.json"])
    artifact_manifest = _load_json_bytes(
        "ARTIFACT_MANIFEST.json", members["ARTIFACT_MANIFEST.json"]
    )
    _verify_artifact_manifest(artifact_manifest, run_id, members)

    return {
        "status": "VERIFIED",
        "formal_success": True,
        "run_id": run_id,
        "certification_status": expected_status,
        "zip_path": str(zip_path),
        "zip_sidecar": str(sidecar),
        "zip_sha256": digest,
        "zip_bytes": zip_path.stat().st_size,
        "zip_member_count": len(REQUIRED_ARTIFACTS) + 1,
        "content_set_sha256": content_set,
        "checks": {
            "sidecar": True,
            "zip_metadata": True,
            "zip_crc": True,
            "package_manifest": True,
            "internal_sha256sums": True,
            "artifact_manifest": True,
            "runtime_identity": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", dest="zip_path", type=Path, required=True)
    parser.add_argument("--sidecar", dest="sidecar_path", type=Path)
    parser.add_argument("--expected-status", default="VERIFIED")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify_package(
            args.zip_path,
            sidecar_path=args.sidecar_path,
            expected_status=args.expected_status,
        )
        exit_code = 0
    except PackageVerificationError as exc:
        report = {
            "status": "FAILED_PACKAGE_VERIFICATION",
            "formal_success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 2
    except Exception as exc:
        report = {
            "status": "FAILED_PACKAGE_VERIFIER_BOOTSTRAP",
            "formal_success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 3
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
