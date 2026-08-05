from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from loto.mlforecast.artifacts import atomic_write_text, sha256_file


@dataclass(frozen=True)
class BundleResult:
    run_id: str
    source_status: str
    zip_path: Path
    sha256_path: Path
    sha256: str
    file_count: int


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON artifact must contain an object: {path}")
    return value


def _safe_relative_path(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"unsafe artifact path in manifest: {value!r}")
    return relative


def _manifest_records(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    payload = _load_json(manifest_path)
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
        relative = _safe_relative_path(path_value)
        canonical = relative.as_posix()
        if canonical in seen:
            raise RuntimeError(f"duplicate artifact path in manifest: {canonical}")
        seen.add(canonical)
        if not isinstance(size_value, int) or size_value < 0:
            raise RuntimeError(f"invalid artifact size for {canonical}")
        if not isinstance(digest_value, str) or len(digest_value) != 64:
            raise RuntimeError(f"invalid artifact SHA-256 for {canonical}")
        path = run_dir.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"manifest artifact is not a regular file: {canonical}")
        actual_size = path.stat().st_size
        actual_digest = sha256_file(path)
        if actual_size != size_value or actual_digest != digest_value:
            raise RuntimeError(
                f"manifest verification failed for {canonical}: "
                f"size={actual_size}/{size_value}, "
                f"sha256={actual_digest}/{digest_value}"
            )
        normalized.append(
            {
                "path": canonical,
                "size_bytes": size_value,
                "sha256": digest_value,
            }
        )
    return sorted(normalized, key=lambda record: record["path"])


def _parse_sha256sums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"unable to read SHA256SUMS: {path}") from exc
    records: dict[str, str] = {}
    for line in lines:
        if not line:
            continue
        digest, separator, name = line.partition("  ")
        if separator != "  " or len(digest) != 64 or not name:
            raise RuntimeError(f"invalid SHA256SUMS line: {line!r}")
        canonical = _safe_relative_path(name).as_posix()
        if canonical in records:
            raise RuntimeError(f"duplicate SHA256SUMS path: {canonical}")
        records[canonical] = digest
    return records


def verify_run_directory(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(
            f"runtime certification directory not found: {run_dir}"
        )
    if run_dir.is_symlink():
        raise RuntimeError(
            f"runtime certification directory must not be a symlink: {run_dir}"
        )

    report_path = run_dir / "RUNTIME_CERTIFICATION.json"
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    sums_path = run_dir / "SHA256SUMS"
    for required in (report_path, manifest_path, sums_path):
        if required.is_symlink() or not required.is_file():
            raise RuntimeError(
                f"required runtime artifact missing: {required.name}"
            )

    report = _load_json(report_path)
    run_id = report.get("run_id")
    status = report.get("status")
    if not isinstance(run_id, str) or run_id != run_dir.name:
        raise RuntimeError(
            "runtime report run_id mismatch: "
            f"report={run_id!r}, directory={run_dir.name!r}"
        )
    if status not in {"RUNTIME_CERTIFIED", "FAILED"}:
        raise RuntimeError(f"runtime report has non-terminal status: {status!r}")

    manifest_records = _manifest_records(run_dir)
    sums_records = _parse_sha256sums(sums_path)
    expected_sums = {
        record["path"]: record["sha256"] for record in manifest_records
    }
    if sums_records != expected_sums:
        raise RuntimeError(
            "SHA256SUMS does not exactly match ARTIFACT_MANIFEST.json"
        )

    if status == "RUNTIME_CERTIFIED":
        required_artifacts = (
            "inputs/mlforecast-1.1.0-py3-none-any.whl",
            "core_ridge_predictions.csv",
            "auto_ridge_predictions.csv",
            "auto_ridge_trials.csv",
        )
        manifest_paths = set(expected_sums)
        missing = [path for path in required_artifacts if path not in manifest_paths]
        if missing:
            raise RuntimeError(
                f"certified run is missing required artifacts: {missing}"
            )
        if not any(
            path.startswith("models/core-ridge/") for path in manifest_paths
        ):
            raise RuntimeError(
                "certified run is missing Core Ridge model artifacts"
            )
        if not any(
            path.startswith("models/auto-ridge/") for path in manifest_paths
        ):
            raise RuntimeError(
                "certified run is missing AutoRidge model artifacts"
            )

    return {
        "run_id": run_id,
        "source_status": status,
        "run_dir": run_dir,
        "manifest_records": manifest_records,
        "manifest_sha256": sha256_file(manifest_path),
        "sums_sha256": sha256_file(sums_path),
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def bundle_run(run_dir: Path, output_dir: Path) -> BundleResult:
    verified = verify_run_directory(run_dir)
    run_id = str(verified["run_id"])
    source_status = str(verified["source_status"])
    resolved_run_dir = Path(verified["run_dir"])
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / f"{run_id}.zip"
    sha256_path = output_dir / f"{run_id}.zip.sha256"
    if zip_path.exists() or sha256_path.exists():
        raise FileExistsError(
            f"runtime bundle already exists for run_id={run_id}"
        )

    source_files = sorted(
        path
        for path in resolved_run_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    expected_source_paths = {
        record["path"] for record in verified["manifest_records"]
    } | {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    actual_source_paths = {
        path.relative_to(resolved_run_dir).as_posix() for path in source_files
    }
    if actual_source_paths != expected_source_paths:
        extra = sorted(actual_source_paths - expected_source_paths)
        missing = sorted(expected_source_paths - actual_source_paths)
        raise RuntimeError(
            "runtime directory file set differs from manifest contract: "
            f"extra={extra}, missing={missing}"
        )

    bundle_report = {
        "bundle_format": 1,
        "run_id": run_id,
        "source_status": source_status,
        "source_file_count": len(source_files),
        "source_manifest_sha256": verified["manifest_sha256"],
        "source_sha256sums_sha256": verified["sums_sha256"],
    }
    bundle_report_bytes = (
        json.dumps(bundle_report, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    entries = [
        (
            f"{run_id}/{source.relative_to(resolved_run_dir).as_posix()}",
            source.read_bytes(),
        )
        for source in source_files
    ]
    entries.append(
        (f"{run_id}/BUNDLE_VERIFICATION.json", bundle_report_bytes)
    )

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-mlforecast-bundle",
        description=(
            "Verify and deterministically bundle one MLForecast "
            "runtime certification run"
        ),
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/mlforecast-runtime-bundles"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = bundle_run(args.run_dir, args.output_dir)
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "source_status": result.source_status,
                "zip_path": str(result.zip_path),
                "sha256_path": str(result.sha256_path),
                "sha256": result.sha256,
                "file_count": result.file_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
