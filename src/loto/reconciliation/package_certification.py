"""Package HierarchicalForecast runtime-certification evidence into a verified ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from loto.reconciliation import runtime_certification as runtime

PRIMARY_ARTIFACTS = (
    "RUNTIME_CERTIFICATION.json",
    "METHOD_RESULTS.json",
    "INPUT_EVIDENCE.json",
    "ARTIFACT_MANIFEST.json",
)
REQUIRED_ARTIFACTS = (*PRIMARY_ARTIFACTS, "SHA256SUMS")
PACKAGE_MANIFEST = "PACKAGE_MANIFEST.json"
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ZIP_COMPRESSION = zipfile.ZIP_STORED
_REGULAR_FILE_MODE = 0o100644


class PackageIntegrityError(RuntimeError):
    """Raised when runtime evidence cannot be packaged without losing integrity."""


class CertificationPackagingError(RuntimeError):
    """Retain certification context when its evidence cannot be packaged."""

    def __init__(self, certification: dict[str, object], cause: Exception) -> None:
        self.certification = certification
        self.cause = cause
        super().__init__(f"{type(cause).__name__}: {cause}")


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


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageIntegrityError(f"cannot read valid JSON from {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackageIntegrityError(f"{path.name} must contain a JSON object")
    return payload


def _safe_filename(value: str) -> str:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise PackageIntegrityError(f"unsafe artifact path in checksum data: {value!r}")
    if candidate.name != value or not value:
        raise PackageIntegrityError(f"invalid artifact filename: {value!r}")
    return value


def _read_checksums(run_dir: Path) -> dict[str, str]:
    checksum_path = run_dir / "SHA256SUMS"
    try:
        rows = checksum_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PackageIntegrityError(f"cannot read SHA256SUMS: {exc}") from exc

    parsed: dict[str, str] = {}
    for row in rows:
        if not row.strip():
            continue
        try:
            digest, filename = row.split("  ", maxsplit=1)
        except ValueError as exc:
            raise PackageIntegrityError(f"invalid SHA256SUMS row: {row!r}") from exc
        filename = _safe_filename(filename)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise PackageIntegrityError(f"invalid SHA-256 digest for {filename}")
        if filename in parsed:
            raise PackageIntegrityError(f"duplicate SHA256SUMS entry: {filename}")
        parsed[filename] = digest

    expected = set(PRIMARY_ARTIFACTS)
    if set(parsed) != expected:
        raise PackageIntegrityError(
            f"SHA256SUMS coverage mismatch: expected={sorted(expected)} actual={sorted(parsed)}"
        )
    return parsed


def _verify_artifact_manifest(run_dir: Path, run_id: str) -> None:
    payload = _load_json(run_dir / "ARTIFACT_MANIFEST.json")
    if payload.get("run_id") != run_id:
        raise PackageIntegrityError("ARTIFACT_MANIFEST run_id does not match directory")
    rows = payload.get("files")
    if not isinstance(rows, list):
        raise PackageIntegrityError("ARTIFACT_MANIFEST files must be a list")

    expected_names = set(PRIMARY_ARTIFACTS[:3])
    actual_names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PackageIntegrityError("ARTIFACT_MANIFEST file row must be an object")
        name = _safe_filename(str(row.get("path", "")))
        if name in actual_names:
            raise PackageIntegrityError(f"duplicate ARTIFACT_MANIFEST entry: {name}")
        actual_names.add(name)
        path = run_dir / name
        if row.get("bytes") != path.stat().st_size:
            raise PackageIntegrityError(f"ARTIFACT_MANIFEST byte count mismatch: {name}")
        if row.get("sha256") != _sha256_file(path):
            raise PackageIntegrityError(f"ARTIFACT_MANIFEST hash mismatch: {name}")
    if actual_names != expected_names:
        raise PackageIntegrityError(
            "ARTIFACT_MANIFEST coverage mismatch: "
            f"expected={sorted(expected_names)} actual={sorted(actual_names)}"
        )


def verify_run_directory(run_dir: Path, *, certification_status: str) -> dict[str, object]:
    """Verify all runtime artifacts before any ZIP is created."""
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise PackageIntegrityError(f"run directory does not exist: {run_dir}")
    run_id = run_dir.name

    for filename in REQUIRED_ARTIFACTS:
        path = run_dir / filename
        if not path.is_file():
            raise PackageIntegrityError(f"required artifact is missing: {filename}")

    checksums = _read_checksums(run_dir)
    for filename, expected_digest in checksums.items():
        actual_digest = _sha256_file(run_dir / filename)
        if actual_digest != expected_digest:
            raise PackageIntegrityError(f"SHA256SUMS verification failed: {filename}")

    certification = _load_json(run_dir / "RUNTIME_CERTIFICATION.json")
    if certification.get("run_id") != run_id:
        raise PackageIntegrityError("RUNTIME_CERTIFICATION run_id does not match directory")
    if certification.get("status") != certification_status:
        raise PackageIntegrityError(
            "certification status mismatch: "
            f"result={certification_status!r} artifact={certification.get('status')!r}"
        )
    recorded_directory = Path(str(certification.get("run_directory", "")))
    if recorded_directory.name != run_id:
        raise PackageIntegrityError("recorded run_directory does not identify the run directory")

    _verify_artifact_manifest(run_dir, run_id)
    files = [
        {
            "path": filename,
            "bytes": (run_dir / filename).stat().st_size,
            "sha256": _sha256_file(run_dir / filename),
        }
        for filename in REQUIRED_ARTIFACTS
    ]
    return {
        "run_id": run_id,
        "certification_status": certification_status,
        "files": files,
        "content_set_sha256": _sha256_bytes(_canonical_json_bytes(files)),
    }


def _zip_info(member_name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(member_name, date_time=_FIXED_ZIP_TIMESTAMP)
    info.compress_type = _ZIP_COMPRESSION
    info.create_system = 3
    info.external_attr = _REGULAR_FILE_MODE << 16
    return info


def _validate_member_name(name: str, *, run_id: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise PackageIntegrityError(f"unsafe ZIP member: {name!r}")
    if len(path.parts) != 2 or path.parts[0] != run_id:
        raise PackageIntegrityError(f"ZIP member is outside expected run prefix: {name!r}")


def _verify_member_metadata(info: zipfile.ZipInfo) -> None:
    if info.is_dir():
        raise PackageIntegrityError(f"ZIP contains directory member: {info.filename!r}")
    if info.flag_bits & 0x1:
        raise PackageIntegrityError(f"ZIP contains encrypted member: {info.filename!r}")
    if info.compress_type != _ZIP_COMPRESSION:
        raise PackageIntegrityError(f"ZIP compression mismatch: {info.filename!r}")
    if info.date_time != _FIXED_ZIP_TIMESTAMP:
        raise PackageIntegrityError(f"ZIP timestamp mismatch: {info.filename!r}")
    if info.create_system != 3:
        raise PackageIntegrityError(f"ZIP creator system mismatch: {info.filename!r}")
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode != _REGULAR_FILE_MODE:
        raise PackageIntegrityError(f"ZIP member mode mismatch: {info.filename!r}")


def _verify_zip(
    zip_path: Path,
    *,
    package_manifest: dict[str, object],
) -> None:
    run_id = str(package_manifest["run_id"])
    expected_names = {
        *(f"{run_id}/{filename}" for filename in REQUIRED_ARTIFACTS),
        f"{run_id}/{PACKAGE_MANIFEST}",
    }
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise PackageIntegrityError("ZIP contains duplicate member names")
            for info in infos:
                _validate_member_name(info.filename, run_id=run_id)
                _verify_member_metadata(info)
            if set(names) != expected_names:
                raise PackageIntegrityError(
                    "ZIP coverage mismatch: "
                    f"expected={sorted(expected_names)} actual={sorted(names)}"
                )
            manifest_name = f"{run_id}/{PACKAGE_MANIFEST}"
            archived_manifest_bytes = archive.read(manifest_name)
            if archived_manifest_bytes != _canonical_json_bytes(package_manifest):
                raise PackageIntegrityError("archived PACKAGE_MANIFEST bytes do not match source")
            for row in package_manifest["files"]:
                name = str(row["path"])
                payload = archive.read(f"{run_id}/{name}")
                if len(payload) != row["bytes"]:
                    raise PackageIntegrityError(f"ZIP byte count mismatch: {name}")
                if _sha256_bytes(payload) != row["sha256"]:
                    raise PackageIntegrityError(f"ZIP hash mismatch: {name}")
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise PackageIntegrityError(f"ZIP verification failed: {exc}") from exc


def _sidecar_path(zip_path: Path) -> Path:
    return Path(f"{zip_path}.sha256")


def _expected_sidecar(zip_path: Path, digest: str) -> str:
    return f"{digest}  {zip_path.name}\n"


def _verify_existing_output(
    zip_path: Path,
    sidecar: Path,
    *,
    expected_digest: str,
    package_manifest: dict[str, object],
) -> bool:
    """Return true when immutable outputs already exist and match exactly."""
    if not zip_path.exists() and not sidecar.exists():
        return False
    if not zip_path.is_file():
        raise PackageIntegrityError(f"existing ZIP path is not a regular file: {zip_path}")
    if _sha256_file(zip_path) != expected_digest:
        raise PackageIntegrityError("existing ZIP differs from deterministic package bytes")
    _verify_zip(zip_path, package_manifest=package_manifest)

    expected_sidecar = _expected_sidecar(zip_path, expected_digest)
    if sidecar.exists():
        if not sidecar.is_file():
            raise PackageIntegrityError(f"existing sidecar is not a regular file: {sidecar}")
        if sidecar.read_text(encoding="utf-8") != expected_sidecar:
            raise PackageIntegrityError("existing ZIP sidecar does not match package digest")
    else:
        _atomic_write_text(sidecar, expected_sidecar)
    return True


def _promote_new_zip(temporary_path: Path, zip_path: Path) -> None:
    """Publish without replacing a pre-existing artifact."""
    try:
        os.link(temporary_path, zip_path)
    except FileExistsError as exc:
        raise PackageIntegrityError(f"ZIP appeared concurrently: {zip_path}") from exc
    except OSError as exc:
        raise PackageIntegrityError(f"cannot publish immutable ZIP: {exc}") from exc


def package_run(run_dir: Path, *, certification_status: str) -> dict[str, object]:
    """Verify one evidence directory, create a deterministic ZIP, and verify the ZIP."""
    run_dir = run_dir.resolve()
    package_manifest = verify_run_directory(
        run_dir,
        certification_status=certification_status,
    )
    manifest_bytes = _canonical_json_bytes(package_manifest)
    zip_path = run_dir.with_suffix(".zip")
    sidecar = _sidecar_path(zip_path)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=zip_path.parent,
        prefix=f".{zip_path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    reused_existing = False
    try:
        with zipfile.ZipFile(
            temporary_path,
            "w",
            compression=_ZIP_COMPRESSION,
            strict_timestamps=True,
        ) as archive:
            run_id = run_dir.name
            for filename in REQUIRED_ARTIFACTS:
                archive.writestr(
                    _zip_info(f"{run_id}/{filename}"),
                    (run_dir / filename).read_bytes(),
                    compress_type=_ZIP_COMPRESSION,
                )
            archive.writestr(
                _zip_info(f"{run_id}/{PACKAGE_MANIFEST}"),
                manifest_bytes,
                compress_type=_ZIP_COMPRESSION,
            )
        _verify_zip(temporary_path, package_manifest=package_manifest)
        digest = _sha256_file(temporary_path)
        reused_existing = _verify_existing_output(
            zip_path,
            sidecar,
            expected_digest=digest,
            package_manifest=package_manifest,
        )
        if not reused_existing:
            _promote_new_zip(temporary_path, zip_path)
            _verify_zip(zip_path, package_manifest=package_manifest)
            _atomic_write_text(sidecar, _expected_sidecar(zip_path, digest))
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "status": "VERIFIED",
        "path": str(zip_path),
        "sha256": digest,
        "sha256_sidecar": str(sidecar),
        "bytes": zip_path.stat().st_size,
        "member_count": len(REQUIRED_ARTIFACTS) + 1,
        "run_id": run_dir.name,
        "certification_status": certification_status,
        "content_set_sha256": package_manifest["content_set_sha256"],
        "reused_existing": reused_existing,
    }


def run_packaged_certification(
    config: runtime.RuntimeCertificationConfig,
) -> dict[str, object]:
    """Run certification, then package evidence regardless of formal certification status."""
    certification = runtime.run_certification(config)
    run_directory = Path(str(certification["run_directory"]))
    try:
        package = package_run(
            run_directory,
            certification_status=str(certification["status"]),
        )
    except Exception as exc:
        raise CertificationPackagingError(certification, exc) from exc
    return {"certification": certification, "package": package}


def _parse_games(value: str) -> tuple[str, ...]:
    if value.strip().lower() == "all":
        return runtime.DEFAULT_GAMES
    return tuple(part.strip() for part in value.split(",") if part.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Certify HierarchicalForecast, verify every artifact, and create a SHA-256-sealed ZIP."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-runtime"),
    )
    parser.add_argument("--games", default="all")
    parser.add_argument("--expected-version", default=runtime.TARGET_VERSION)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--insample-size", type=int, default=32)
    parser.add_argument("--coherence-tolerance", type=float, default=1e-8)
    return parser


def _packaging_error_payload(exc: CertificationPackagingError) -> dict[str, object]:
    certification = exc.certification
    return {
        "status": "FAILED_PACKAGING",
        "formal_success": False,
        "phase": "package",
        "error": f"{type(exc.cause).__name__}: {exc.cause}",
        "run_id": certification.get("run_id"),
        "run_directory": certification.get("run_directory"),
        "certification_status": certification.get("status"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = runtime.RuntimeCertificationConfig(
            output_root=args.output_root,
            games=_parse_games(args.games),
            expected_version=args.expected_version,
            seed=args.seed,
            horizon=args.horizon,
            insample_size=args.insample_size,
            coherence_tolerance=args.coherence_tolerance,
        )
    except Exception as exc:
        error = {
            "status": "INVALID_CONFIGURATION",
            "formal_success": False,
            "phase": "configuration",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(error, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    try:
        result = run_packaged_certification(config)
    except CertificationPackagingError as exc:
        print(
            json.dumps(
                _packaging_error_payload(exc),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    except Exception as exc:
        error = {
            "status": "FAILED_CERTIFICATION_HARNESS",
            "formal_success": False,
            "phase": "certification",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(error, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["certification"]["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
