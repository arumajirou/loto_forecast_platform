from __future__ import annotations

import argparse
import io
import json
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from loto.mlforecast.bundle import verify_bundle_archive
from loto.mlforecast.final_evidence_support import (
    DIGEST,
    FIXED_TIME,
    REQUIRED_HANDOFF,
    RUN_ID,
    build,
    load_json,
    regular,
    reject_symlink_components,
    safe_name,
    sha_bytes,
    sha_file,
    validate_source,
)
from loto.mlforecast.handoff_guard import verify_guarded_handoff


def verify_nested(files: dict[str, bytes], status: str, gate: dict[str, Any]) -> dict[str, Any]:
    handoff_zips = [name for name in files if name.startswith("handoff/") and name.endswith(".zip")]
    if len(handoff_zips) != 1:
        raise RuntimeError("expected one embedded handoff ZIP")
    runtime_zips = [name for name in files if name.startswith("runtime/") and name.endswith(".zip")]
    with tempfile.TemporaryDirectory(prefix="mlforecast-final-evidence-") as temp:
        temp_root = Path(temp)
        handoff_name = handoff_zips[0]
        handoff_sidecar = f"{handoff_name}.sha256"
        if handoff_sidecar not in files:
            raise RuntimeError("embedded handoff sidecar missing")
        handoff_zip = temp_root / Path(handoff_name).name
        handoff_sum = temp_root / Path(handoff_sidecar).name
        handoff_zip.write_bytes(files[handoff_name])
        handoff_sum.write_bytes(files[handoff_sidecar])
        handoff = verify_guarded_handoff(handoff_zip, handoff_sum)
        with zipfile.ZipFile(io.BytesIO(files[handoff_name])) as archive:
            missing = REQUIRED_HANDOFF - set(archive.namelist())
        if missing:
            raise RuntimeError(f"embedded handoff omits final-evidence files: {sorted(missing)}")
        runtime: dict[str, Any] | None = None
        if runtime_zips:
            if len(runtime_zips) != 1:
                raise RuntimeError("multiple embedded runtime ZIPs")
            runtime_name = runtime_zips[0]
            runtime_sidecar = f"{runtime_name}.sha256"
            runtime_report = runtime_name[:-4] + ".verification.json"
            if runtime_sidecar not in files or runtime_report not in files:
                raise RuntimeError("embedded runtime evidence incomplete")
            runtime_zip = temp_root / Path(runtime_name).name
            runtime_sum = temp_root / Path(runtime_sidecar).name
            runtime_zip.write_bytes(files[runtime_name])
            runtime_sum.write_bytes(files[runtime_sidecar])
            result = verify_bundle_archive(runtime_zip, runtime_sum)
            report = load_json(files[runtime_report], "runtime verification report")
            if report.get("status") != "BUNDLE_VERIFIED":
                raise RuntimeError("runtime report is not BUNDLE_VERIFIED")
            if report.get("source_status") != result.source_status:
                raise RuntimeError("runtime source status mismatch")
            if (
                status == "FINAL_VERIFICATION_PASSED"
                and result.source_status != "RUNTIME_CERTIFIED"
            ):
                raise RuntimeError("passed final Run lacks certified runtime")
            runtime = {"status": "BUNDLE_VERIFIED", "source_status": result.source_status}
        elif status == "FINAL_VERIFICATION_PASSED":
            raise RuntimeError("passed final Run lacks runtime evidence")
        if set(gate.get("runtime_files", [])) != {
            Path(name).name for name in files if name.startswith("runtime/")
        }:
            raise RuntimeError("final gate runtime file list mismatch")
    return {"handoff_status": handoff.get("status"), "runtime": runtime}


def verify(
    archive_path: Path,
    sidecar_path: Path,
    report_path: Path | None = None,
    *,
    max_files: int = 100_000,
    max_bytes: int = 512 * 1024**2,
) -> dict[str, Any]:
    archive_path = regular(archive_path, "final-evidence ZIP")
    sidecar_path = regular(sidecar_path, "final-evidence sidecar")
    lines = sidecar_path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise RuntimeError("invalid final-evidence sidecar")
    digest, separator, name = lines[0].partition("  ")
    if separator != "  " or name != archive_path.name or DIGEST.fullmatch(digest) is None:
        raise RuntimeError("invalid final-evidence sidecar")
    if sha_file(archive_path) != digest:
        raise RuntimeError("final-evidence SHA-256 mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > max_files or sum(item.file_size for item in infos) > max_bytes:
            raise RuntimeError("final-evidence archive limit exceeded")
        names = [item.filename for item in infos]
        if names != sorted(names) or len(names) != len(set(names)):
            raise RuntimeError("final-evidence entries must be unique and sorted")
        for item in infos:
            safe_name(item.filename)
            mode = item.external_attr >> 16
            if item.is_dir() or stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise RuntimeError(f"unsafe final-evidence member: {item.filename}")
            if item.flag_bits & 1 or item.date_time != FIXED_TIME:
                raise RuntimeError(f"invalid final-evidence member: {item.filename}")
        if archive.testzip() is not None:
            raise RuntimeError("final-evidence CRC failure")
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise RuntimeError("final-evidence must contain one Run ID")
        run_id = roots.pop()
        if RUN_ID.fullmatch(run_id) is None:
            raise RuntimeError("invalid final-evidence Run ID")
        prefix = f"{run_id}/"
        bundle_name = f"{prefix}FINAL_EVIDENCE_BUNDLE.json"
        if bundle_name not in names:
            raise RuntimeError("final-evidence bundle report missing")
        bundle = load_json(archive.read(bundle_name), "FINAL_EVIDENCE_BUNDLE.json")
        files = {name[len(prefix) :]: archive.read(name) for name in names if name != bundle_name}
        status, gate = validate_source(files, run_id)
        checks = {
            "format": 1,
            "status": "FINAL_EVIDENCE_BUNDLED",
            "run_id": run_id,
            "source_status": status,
            "source_gate_status": gate["status"],
            "manifest_sha256": sha_bytes(files["ARTIFACT_MANIFEST.json"]),
            "sums_sha256": sha_bytes(files["SHA256SUMS"]),
            "gate_sha256": sha_bytes(files["FINAL_GATE_VERIFICATION.json"]),
            "source_file_count": len(files),
        }
        for key, expected in checks.items():
            if bundle.get(key) != expected:
                raise RuntimeError(f"final-evidence bundle mismatch: {key}")
        nested = verify_nested(files, status, gate)
    result = {
        "status": "FINAL_EVIDENCE_VERIFIED",
        "verified_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "source_status": status,
        "zip_sha256": digest,
        **nested,
    }
    if report_path is not None:
        report = reject_symlink_components(
            report_path,
            "final-evidence verification report",
        )
        if report.exists() or report.is_symlink():
            raise FileExistsError(f"verification report exists: {report}")
        report.parent.mkdir(parents=True, exist_ok=True)
        reject_symlink_components(
            report.parent,
            "final-evidence verification report directory",
        )
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loto-mlforecast-final-evidence")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--sha256", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.build:
        if args.run_dir is None or args.output_dir is None:
            raise SystemExit("--build requires --run-dir and --output-dir")
        archive, sidecar = build(args.run_dir, args.output_dir)
        result = {"status": "FINAL_EVIDENCE_BUNDLED", "zip": str(archive), "sha256": str(sidecar)}
    else:
        if args.zip is None or args.sha256 is None:
            raise SystemExit("--verify requires --zip and --sha256")
        result = verify(args.zip, args.sha256, args.report)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
