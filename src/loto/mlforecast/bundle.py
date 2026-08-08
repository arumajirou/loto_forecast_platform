from __future__ import annotations

import argparse
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from loto.mlforecast.artifacts import atomic_write_text, sha256_bytes, sha256_file


BUNDLE_FORMAT = 1
RUN_ID_PATTERN = re.compile(r"^mlforecast-runtime-\d{8}-\d{6}-\d{6}$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FIXED_ZIP_DATETIME = (1980, 1, 1, 0, 0, 0)
DEFAULT_MAX_FILES = 100_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class BundleResult:
    run_id: str
    source_status: str
    zip_path: Path
    sha256_path: Path
    sha256: str
    file_count: int


@dataclass(frozen=True)
class BundleVerificationResult:
    run_id: str
    source_status: str
    zip_path: Path
    sha256: str
    file_count: int
    uncompressed_bytes: int
    report_path: Path | None = None


def _load_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid JSON artifact: {label}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON artifact must contain an object: {label}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _load_json_bytes(path.read_bytes(), label=str(path))
    except OSError as exc:
        raise RuntimeError(f"unable to read JSON artifact: {path}") from exc


def _safe_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise RuntimeError(f"unsafe artifact path: {value!r}")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != value
    ):
        raise RuntimeError(f"unsafe artifact path: {value!r}")
    return relative


def _validate_digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or DIGEST_PATTERN.fullmatch(value) is None:
        raise RuntimeError(f"invalid SHA-256 digest for {label}")
    return value


def _resolve_directory(path: Path, *, label: str) -> Path:
    absolute = path.absolute()
    if absolute.is_symlink():
        raise RuntimeError(f"{label} must not be a symlink: {absolute}")
    if not absolute.is_dir():
        raise FileNotFoundError(f"{label} not found: {absolute}")
    return absolute.resolve(strict=True)


def _regular_file_within(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"artifact path traverses a symlink: {relative.as_posix()}")
    if not current.is_file():
        raise RuntimeError(f"manifest artifact is not a regular file: {relative.as_posix()}")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"artifact resolves outside runtime directory: {relative.as_posix()}"
        ) from exc
    return resolved


def _parse_manifest_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("artifacts")
    if not isinstance(records, list):
        raise RuntimeError("ARTIFACT_MANIFEST.json must contain an artifacts list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("artifact manifest records must be objects")
        path_value = record.get("path")
        size_value = record.get("size_bytes")
        digest_value = record.get("sha256")
        if not isinstance(path_value, str):
            raise RuntimeError("artifact manifest path must be a string")
        canonical = _safe_relative_path(path_value).as_posix()
        if canonical in seen:
            raise RuntimeError(f"duplicate artifact path in manifest: {canonical}")
        seen.add(canonical)
        if not isinstance(size_value, int) or isinstance(size_value, bool) or size_value < 0:
            raise RuntimeError(f"invalid artifact size for {canonical}")
        digest = _validate_digest(digest_value, label=canonical)
        normalized.append({"path": canonical, "size_bytes": size_value, "sha256": digest})
    return sorted(normalized, key=lambda record: record["path"])


def _parse_sha256sums_text(text: str) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            continue
        digest, separator, name = line.partition("  ")
        if separator != "  " or not name:
            raise RuntimeError(f"invalid SHA256SUMS line: {line!r}")
        digest = _validate_digest(digest, label=name)
        canonical = _safe_relative_path(name).as_posix()
        if canonical in records:
            raise RuntimeError(f"duplicate SHA256SUMS path: {canonical}")
        records[canonical] = digest
    return records


def _parse_sha256sums(path: Path) -> dict[str, str]:
    try:
        return _parse_sha256sums_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"unable to read SHA256SUMS: {path}") from exc


def _validate_terminal_report(report: dict[str, Any], *, expected_run_id: str) -> str:
    run_id = report.get("run_id")
    status = report.get("status")
    if run_id != expected_run_id:
        raise RuntimeError(
            f"runtime report run_id mismatch: report={run_id!r}, expected={expected_run_id!r}"
        )
    if status not in {"RUNTIME_CERTIFIED", "FAILED"}:
        raise RuntimeError(f"runtime report has non-terminal status: {status!r}")
    return str(status)


def _validate_certified_artifacts(status: str, manifest_paths: set[str]) -> None:
    if status != "RUNTIME_CERTIFIED":
        return
    required_artifacts = (
        "inputs/mlforecast-1.1.0-py3-none-any.whl",
        "core_ridge_predictions.csv",
        "auto_ridge_predictions.csv",
        "auto_ridge_trials.csv",
    )
    missing = [path for path in required_artifacts if path not in manifest_paths]
    if missing:
        raise RuntimeError(f"certified run is missing required artifacts: {missing}")
    if not any(path.startswith("models/core-ridge/") for path in manifest_paths):
        raise RuntimeError("certified run is missing Core Ridge model artifacts")
    if not any(path.startswith("models/auto-ridge/") for path in manifest_paths):
        raise RuntimeError("certified run is missing AutoRidge model artifacts")


def verify_run_directory(run_dir: Path) -> dict[str, Any]:
    raw_run_dir = run_dir.absolute()
    if raw_run_dir.is_symlink():
        raise RuntimeError(f"runtime certification directory must not be a symlink: {raw_run_dir}")
    run_dir = _resolve_directory(raw_run_dir, label="runtime certification directory")
    if RUN_ID_PATTERN.fullmatch(run_dir.name) is None:
        raise RuntimeError(f"invalid runtime certification directory name: {run_dir.name}")

    for candidate in run_dir.rglob("*"):
        if candidate.is_symlink():
            raise RuntimeError(
                "runtime certification directory contains a symlink: "
                f"{candidate.relative_to(run_dir).as_posix()}"
            )

    report_path = _regular_file_within(run_dir, PurePosixPath("RUNTIME_CERTIFICATION.json"))
    manifest_path = _regular_file_within(run_dir, PurePosixPath("ARTIFACT_MANIFEST.json"))
    sums_path = _regular_file_within(run_dir, PurePosixPath("SHA256SUMS"))

    report = _load_json(report_path)
    status = _validate_terminal_report(report, expected_run_id=run_dir.name)
    manifest_records = _parse_manifest_payload(_load_json(manifest_path))

    for record in manifest_records:
        relative = _safe_relative_path(str(record["path"]))
        path = _regular_file_within(run_dir, relative)
        actual_size = path.stat().st_size
        actual_digest = sha256_file(path)
        if actual_size != record["size_bytes"] or actual_digest != record["sha256"]:
            raise RuntimeError(
                f"manifest verification failed for {record['path']}: "
                f"size={actual_size}/{record['size_bytes']}, "
                f"sha256={actual_digest}/{record['sha256']}"
            )

    sums_records = _parse_sha256sums(sums_path)
    expected_sums = {str(record["path"]): str(record["sha256"]) for record in manifest_records}
    if sums_records != expected_sums:
        raise RuntimeError("SHA256SUMS does not exactly match ARTIFACT_MANIFEST.json")

    manifest_paths = set(expected_sums)
    _validate_certified_artifacts(status, manifest_paths)

    source_files = sorted(path for path in run_dir.rglob("*") if path.is_file())
    expected_source_paths = manifest_paths | {
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }
    actual_source_paths = {path.relative_to(run_dir).as_posix() for path in source_files}
    if actual_source_paths != expected_source_paths:
        extra = sorted(actual_source_paths - expected_source_paths)
        missing = sorted(expected_source_paths - actual_source_paths)
        raise RuntimeError(
            "runtime directory file set differs from manifest contract: "
            f"extra={extra}, missing={missing}"
        )

    return {
        "run_id": run_dir.name,
        "source_status": status,
        "run_dir": run_dir,
        "source_files": source_files,
        "manifest_records": manifest_records,
        "manifest_sha256": sha256_file(manifest_path),
        "sums_sha256": sha256_file(sums_path),
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_DATETIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _output_directory(path: Path, *, run_dir: Path) -> Path:
    absolute = path.absolute()
    if absolute.is_symlink():
        raise RuntimeError(f"bundle output directory must not be a symlink: {absolute}")
    absolute.mkdir(parents=True, exist_ok=True)
    resolved = absolute.resolve(strict=True)
    try:
        resolved.relative_to(run_dir)
    except ValueError:
        return resolved
    raise RuntimeError("bundle output directory must not be inside the source run directory")


def bundle_run(run_dir: Path, output_dir: Path) -> BundleResult:
    verified = verify_run_directory(run_dir)
    run_id = str(verified["run_id"])
    source_status = str(verified["source_status"])
    resolved_run_dir = Path(verified["run_dir"])
    output_dir = _output_directory(output_dir, run_dir=resolved_run_dir)

    zip_path = output_dir / f"{run_id}.zip"
    sha256_path = output_dir / f"{run_id}.zip.sha256"
    if zip_path.exists() or sha256_path.exists():
        raise FileExistsError(f"runtime bundle already exists for run_id={run_id}")

    source_files = list(verified["source_files"])
    bundle_report = {
        "bundle_format": BUNDLE_FORMAT,
        "run_id": run_id,
        "source_status": source_status,
        "source_file_count": len(source_files),
        "source_manifest_sha256": verified["manifest_sha256"],
        "source_sha256sums_sha256": verified["sums_sha256"],
    }
    bundle_report_bytes = (json.dumps(bundle_report, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

    entries = [
        (
            f"{run_id}/{source.relative_to(resolved_run_dir).as_posix()}",
            source.read_bytes(),
        )
        for source in source_files
    ]
    entries.append((f"{run_id}/BUNDLE_VERIFICATION.json", bundle_report_bytes))

    temporary = zip_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name, payload in sorted(entries):
                archive.writestr(_zip_info(name), payload)
        verify_bundle_archive(temporary)
        temporary.replace(zip_path)
    finally:
        temporary.unlink(missing_ok=True)

    digest = sha256_file(zip_path)
    atomic_write_text(sha256_path, f"{digest}  {zip_path.name}\n")
    return BundleResult(
        run_id=run_id,
        source_status=source_status,
        zip_path=zip_path,
        sha256_path=sha256_path,
        sha256=digest,
        file_count=len(source_files) + 1,
    )


def _read_sidecar(path: Path, *, expected_filename: str) -> str:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"unable to read bundle SHA-256 sidecar: {path}") from exc
    if len(lines) != 1:
        raise RuntimeError("bundle SHA-256 sidecar must contain exactly one non-empty line")
    digest, separator, filename = lines[0].partition("  ")
    if separator != "  " or filename != expected_filename:
        raise RuntimeError("bundle SHA-256 sidecar filename mismatch")
    return _validate_digest(digest, label=expected_filename)


def _archive_file_map(
    archive: zipfile.ZipFile,
    *,
    max_files: int,
    max_uncompressed_bytes: int,
) -> tuple[str, dict[str, zipfile.ZipInfo], int]:
    infos = archive.infolist()
    if not infos or len(infos) > max_files:
        raise RuntimeError(f"invalid bundle entry count: observed={len(infos)}, max={max_files}")
    if archive.testzip() is not None:
        raise RuntimeError("bundle ZIP CRC verification failed")

    files: dict[str, zipfile.ZipInfo] = {}
    roots: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        name = info.filename
        if name.endswith("/") or info.is_dir():
            raise RuntimeError(f"bundle must not contain directory entries: {name!r}")
        relative = _safe_relative_path(name)
        if len(relative.parts) < 2:
            raise RuntimeError(f"bundle entry lacks run-id prefix: {name!r}")
        roots.add(relative.parts[0])
        canonical = relative.as_posix()
        if canonical in files:
            raise RuntimeError(f"duplicate bundle entry: {canonical}")
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if file_type not in {0, stat.S_IFREG}:
            raise RuntimeError(f"bundle contains a non-regular entry: {canonical}")
        if info.flag_bits & 0x1:
            raise RuntimeError(f"bundle contains an encrypted entry: {canonical}")
        if info.file_size < 0:
            raise RuntimeError(f"bundle entry has invalid size: {canonical}")
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed_bytes:
            raise RuntimeError(
                "bundle exceeds maximum uncompressed size: "
                f"observed={total_uncompressed}, max={max_uncompressed_bytes}"
            )
        files[canonical] = info

    if len(roots) != 1:
        raise RuntimeError(f"bundle must contain exactly one run-id root: {sorted(roots)}")
    run_id = next(iter(roots))
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RuntimeError(f"invalid bundle run-id root: {run_id!r}")
    return run_id, files, total_uncompressed


def verify_bundle_archive(
    zip_path: Path,
    sha256_path: Path | None = None,
    *,
    report_path: Path | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> BundleVerificationResult:
    raw_zip_path = zip_path.absolute()
    if raw_zip_path.is_symlink() or not raw_zip_path.is_file():
        raise FileNotFoundError(f"bundle ZIP is not a regular file: {raw_zip_path}")
    zip_path = raw_zip_path.resolve(strict=True)
    digest = sha256_file(zip_path)
    if sha256_path is not None:
        raw_sidecar = sha256_path.absolute()
        if raw_sidecar.is_symlink() or not raw_sidecar.is_file():
            raise FileNotFoundError(f"bundle SHA-256 sidecar is not a regular file: {raw_sidecar}")
        expected_digest = _read_sidecar(
            raw_sidecar.resolve(strict=True), expected_filename=zip_path.name
        )
        if digest != expected_digest:
            raise RuntimeError(
                f"bundle ZIP SHA-256 mismatch: expected={expected_digest}, actual={digest}"
            )

    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"invalid bundle ZIP: {zip_path}") from exc

    with archive:
        run_id, files, total_uncompressed = _archive_file_map(
            archive,
            max_files=max_files,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        prefix = f"{run_id}/"
        required_names = {
            f"{prefix}BUNDLE_VERIFICATION.json",
            f"{prefix}RUNTIME_CERTIFICATION.json",
            f"{prefix}ARTIFACT_MANIFEST.json",
            f"{prefix}SHA256SUMS",
        }
        missing_required = sorted(required_names - set(files))
        if missing_required:
            raise RuntimeError(f"bundle is missing required entries: {missing_required}")

        bundle_report_bytes = archive.read(files[f"{prefix}BUNDLE_VERIFICATION.json"])
        runtime_report_bytes = archive.read(files[f"{prefix}RUNTIME_CERTIFICATION.json"])
        manifest_bytes = archive.read(files[f"{prefix}ARTIFACT_MANIFEST.json"])
        sums_bytes = archive.read(files[f"{prefix}SHA256SUMS"])

        bundle_report = _load_json_bytes(bundle_report_bytes, label="BUNDLE_VERIFICATION.json")
        runtime_report = _load_json_bytes(runtime_report_bytes, label="RUNTIME_CERTIFICATION.json")
        manifest_records = _parse_manifest_payload(
            _load_json_bytes(manifest_bytes, label="ARTIFACT_MANIFEST.json")
        )
        try:
            sums_text = sums_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("SHA256SUMS must be valid UTF-8") from exc
        sums_records = _parse_sha256sums_text(sums_text)

        if bundle_report.get("bundle_format") != BUNDLE_FORMAT:
            raise RuntimeError(f"unsupported bundle format: {bundle_report.get('bundle_format')!r}")
        if bundle_report.get("run_id") != run_id:
            raise RuntimeError("bundle report run_id mismatch")
        source_status = _validate_terminal_report(runtime_report, expected_run_id=run_id)
        if bundle_report.get("source_status") != source_status:
            raise RuntimeError("bundle source status disagrees with runtime report")
        if bundle_report.get("source_manifest_sha256") != sha256_bytes(manifest_bytes):
            raise RuntimeError("bundle source manifest digest mismatch")
        if bundle_report.get("source_sha256sums_sha256") != sha256_bytes(sums_bytes):
            raise RuntimeError("bundle source SHA256SUMS digest mismatch")

        expected_sums = {str(record["path"]): str(record["sha256"]) for record in manifest_records}
        if sums_records != expected_sums:
            raise RuntimeError("bundled SHA256SUMS does not exactly match bundled manifest")

        expected_names = {f"{prefix}{record['path']}" for record in manifest_records} | {
            f"{prefix}ARTIFACT_MANIFEST.json",
            f"{prefix}SHA256SUMS",
            f"{prefix}BUNDLE_VERIFICATION.json",
        }
        if set(files) != expected_names:
            extra = sorted(set(files) - expected_names)
            missing = sorted(expected_names - set(files))
            raise RuntimeError(
                f"bundle file set differs from manifest contract: extra={extra}, missing={missing}"
            )

        source_file_count = bundle_report.get("source_file_count")
        expected_source_file_count = len(manifest_records) + 2
        if (
            not isinstance(source_file_count, int)
            or isinstance(source_file_count, bool)
            or source_file_count != expected_source_file_count
        ):
            raise RuntimeError(
                "bundle source file count mismatch: "
                f"report={source_file_count!r}, expected={expected_source_file_count}"
            )

        for record in manifest_records:
            name = f"{prefix}{record['path']}"
            payload = archive.read(files[name])
            if len(payload) != record["size_bytes"]:
                raise RuntimeError(f"bundled artifact size mismatch: {record['path']}")
            actual_digest = sha256_bytes(payload)
            if actual_digest != record["sha256"]:
                raise RuntimeError(f"bundled artifact SHA-256 mismatch: {record['path']}")

        _validate_certified_artifacts(source_status, set(expected_sums))

    result_report_path: Path | None = None
    if report_path is not None:
        result_report_path = report_path.absolute()
        if result_report_path.exists():
            raise FileExistsError(
                f"bundle verification report already exists: {result_report_path}"
            )
        verification_report = {
            "status": "BUNDLE_VERIFIED",
            "verified_at": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "source_status": source_status,
            "zip_path": str(zip_path),
            "zip_sha256": digest,
            "file_count": len(files),
            "uncompressed_bytes": total_uncompressed,
        }
        atomic_write_text(
            result_report_path,
            json.dumps(verification_report, indent=2, sort_keys=True) + "\n",
        )

    return BundleVerificationResult(
        run_id=run_id,
        source_status=source_status,
        zip_path=zip_path,
        sha256=digest,
        file_count=len(files),
        uncompressed_bytes=total_uncompressed,
        report_path=result_report_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-mlforecast-bundle",
        description="Create or independently verify an MLForecast runtime bundle",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-dir", type=Path)
    mode.add_argument("--verify-zip", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/mlforecast-runtime-bundles"),
    )
    parser.add_argument("--sha256-file", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument(
        "--max-uncompressed-bytes",
        type=int,
        default=DEFAULT_MAX_UNCOMPRESSED_BYTES,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.run_dir is not None:
        result = bundle_run(args.run_dir, args.output_dir)
        payload = {
            "mode": "create",
            "run_id": result.run_id,
            "source_status": result.source_status,
            "zip_path": str(result.zip_path),
            "sha256_path": str(result.sha256_path),
            "sha256": result.sha256,
            "file_count": result.file_count,
        }
    else:
        result = verify_bundle_archive(
            args.verify_zip,
            args.sha256_file,
            report_path=args.report,
            max_files=args.max_files,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
        payload = {
            "mode": "verify",
            "status": "BUNDLE_VERIFIED",
            "run_id": result.run_id,
            "source_status": result.source_status,
            "zip_path": str(result.zip_path),
            "sha256": result.sha256,
            "file_count": result.file_count,
            "uncompressed_bytes": result.uncompressed_bytes,
            "report_path": None if result.report_path is None else str(result.report_path),
        }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
