"""Portable immutable publication for HierarchicalForecast certification packages.

The legacy module remains the source of truth for evidence verification and deterministic ZIP
construction. This layer replaces only final ZIP/sidecar publication so formal certification also
works on filesystems where hard links are unavailable, including common WSL mounted-drive setups.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO

from loto.reconciliation import package_certification as legacy

PRIMARY_ARTIFACTS = legacy.PRIMARY_ARTIFACTS
REQUIRED_ARTIFACTS = legacy.REQUIRED_ARTIFACTS
PACKAGE_MANIFEST = legacy.PACKAGE_MANIFEST
_FIXED_ZIP_TIMESTAMP = legacy._FIXED_ZIP_TIMESTAMP
_ZIP_COMPRESSION = legacy._ZIP_COMPRESSION
_REGULAR_FILE_MODE = legacy._REGULAR_FILE_MODE
PackageIntegrityError = legacy.PackageIntegrityError
CertificationPackagingError = legacy.CertificationPackagingError
runtime = legacy.runtime
verify_run_directory = legacy.verify_run_directory
_verify_zip = legacy._verify_zip
_sha256_file = legacy._sha256_file
_canonical_json_bytes = legacy._canonical_json_bytes
_zip_info = legacy._zip_info

_COPY_CHUNK_SIZE = 1024 * 1024


def _write_exclusive(path: Path, data: bytes) -> None:
    """Create a file and fsync it without replacing any existing path."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(path, flags, 0o644)
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            path.unlink(missing_ok=True)
        raise


def _expected_sidecar(zip_path: Path, digest: str) -> str:
    return f"{digest}  {zip_path.name}\n"


def _sidecar_path(zip_path: Path) -> Path:
    return Path(f"{zip_path}.sha256")


def _publish_sidecar(zip_path: Path, digest: str) -> None:
    sidecar = _sidecar_path(zip_path)
    expected = _expected_sidecar(zip_path, digest)
    try:
        _write_exclusive(sidecar, expected.encode("utf-8"))
    except FileExistsError:
        if not sidecar.is_file() or sidecar.is_symlink():
            raise PackageIntegrityError(
                f"existing sidecar is not a regular file: {sidecar}"
            )
        if sidecar.read_text(encoding="utf-8") != expected:
            raise PackageIntegrityError(
                "existing ZIP sidecar does not match package digest"
            )


def _verify_existing_output(
    zip_path: Path,
    sidecar: Path,
    *,
    expected_digest: str,
    package_manifest: dict[str, object],
) -> bool:
    if not zip_path.exists() and not sidecar.exists():
        return False
    if not zip_path.is_file() or zip_path.is_symlink():
        raise PackageIntegrityError(
            f"existing ZIP path is not a regular file: {zip_path}"
        )
    if _sha256_file(zip_path) != expected_digest:
        raise PackageIntegrityError(
            "existing ZIP differs from deterministic package bytes"
        )
    _verify_zip(zip_path, package_manifest=package_manifest)
    _publish_sidecar(zip_path, expected_digest)
    return True


def _copy_stream(source: BinaryIO, destination: BinaryIO) -> None:
    while True:
        chunk = source.read(_COPY_CHUNK_SIZE)
        if not chunk:
            return
        destination.write(chunk)


def _copy_exclusive(
    temporary_path: Path,
    zip_path: Path,
    expected_digest: str,
) -> str:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(zip_path, flags, 0o644)
        created = True
        with temporary_path.open("rb") as source, os.fdopen(
            descriptor,
            "wb",
        ) as destination:
            descriptor = None
            _copy_stream(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        if _sha256_file(zip_path) != expected_digest:
            raise PackageIntegrityError("exclusive-copy ZIP digest mismatch")
        return "exclusive_copy"
    except FileExistsError as exc:
        raise PackageIntegrityError(
            f"ZIP appeared concurrently: {zip_path}"
        ) from exc
    except Exception as exc:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            zip_path.unlink(missing_ok=True)
        if isinstance(exc, PackageIntegrityError):
            raise
        raise PackageIntegrityError(
            f"cannot publish immutable ZIP by copy: {exc}"
        ) from exc


def _promote_new_zip(
    temporary_path: Path,
    zip_path: Path,
    *,
    expected_digest: str,
) -> str:
    """Publish without replacing a pre-existing artifact."""
    try:
        os.link(temporary_path, zip_path)
    except FileExistsError as exc:
        raise PackageIntegrityError(
            f"ZIP appeared concurrently: {zip_path}"
        ) from exc
    except OSError:
        return _copy_exclusive(temporary_path, zip_path, expected_digest)

    try:
        if _sha256_file(zip_path) != expected_digest:
            raise PackageIntegrityError("hard-link ZIP digest mismatch")
    except Exception:
        zip_path.unlink(missing_ok=True)
        raise
    return "hardlink"


def package_run(
    run_dir: Path,
    *,
    certification_status: str,
) -> dict[str, object]:
    """Verify, deterministically archive, and publish one runtime evidence directory."""
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
    publication_method = "reused_existing"
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
            publication_method = _promote_new_zip(
                temporary_path,
                zip_path,
                expected_digest=digest,
            )
            try:
                _verify_zip(zip_path, package_manifest=package_manifest)
                if _sha256_file(zip_path) != digest:
                    raise PackageIntegrityError("published ZIP digest changed")
                _publish_sidecar(zip_path, digest)
            except Exception:
                zip_path.unlink(missing_ok=True)
                raise
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
        "publication_method": publication_method,
    }


def run_packaged_certification(
    config: runtime.RuntimeCertificationConfig,
) -> dict[str, object]:
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


def build_parser() -> argparse.ArgumentParser:
    return legacy.build_parser()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = runtime.RuntimeCertificationConfig(
            output_root=args.output_root,
            games=legacy._parse_games(args.games),
            expected_version=args.expected_version,
            seed=args.seed,
            horizon=args.horizon,
            insample_size=args.insample_size,
            coherence_tolerance=args.coherence_tolerance,
        )
    except Exception as exc:
        payload = {
            "status": "INVALID_CONFIGURATION",
            "formal_success": False,
            "phase": "configuration",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    try:
        result = run_packaged_certification(config)
    except CertificationPackagingError as exc:
        print(
            json.dumps(
                legacy._packaging_error_payload(exc),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    except Exception as exc:
        payload = {
            "status": "FAILED_CERTIFICATION_HARNESS",
            "formal_success": False,
            "phase": "certification",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["certification"]["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
