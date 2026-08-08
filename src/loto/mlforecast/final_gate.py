from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from loto.mlforecast.artifacts import atomic_write_text, sha256_file
from loto.mlforecast.handoff_guard import verify_guarded_handoff

DIGEST = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^mlforecast-final-[0-9]{8}-[0-9]{6}-[0-9]+-[0-9a-f]{12}$")
REQUIRED_HANDOFF_FILES = {
    "docs/mlforecast/run_final_verification_complete.sh",
    "src/loto/mlforecast/final_gate.py",
    "tests/mlforecast/test_final_gate.py",
}
EXCLUDED = {
    "ARTIFACT_MANIFEST.json",
    "SHA256SUMS",
    "FINAL_GATE_VERIFICATION.json",
}


def _safe(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise RuntimeError(f"unsafe final-gate path: {value!r}")
    return path


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid {label}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain an object")
    return value


def _sidecar(zip_path: Path) -> str:
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    lines = sidecar.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise RuntimeError(f"invalid sidecar line count: {sidecar.name}")
    digest, separator, name = lines[0].partition("  ")
    if separator != "  " or name != zip_path.name or DIGEST.fullmatch(digest) is None:
        raise RuntimeError(f"invalid sidecar format: {sidecar.name}")
    if sha256_file(zip_path) != digest:
        raise RuntimeError(f"ZIP SHA-256 mismatch: {zip_path.name}")
    return digest


def _runtime_value(log: Path, key: str) -> Path:
    prefix = f"{key}="
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            value = Path(line[len(prefix) :]).expanduser().absolute()
            if value.is_symlink() or not value.is_file():
                raise RuntimeError(f"runtime evidence is not a regular file: {value}")
            return value.resolve()
    raise RuntimeError(f"runtime log does not contain {key}")


def _copy_runtime(run_dir: Path, source_status: str) -> list[Path]:
    logs = list((run_dir / "logs").glob("*-installed-runtime.log"))
    if len(logs) != 1:
        if source_status == "FINAL_VERIFICATION_PASSED":
            raise RuntimeError("passed final run lacks one installed-runtime log")
        return []
    log = logs[0]
    keys = ("BUNDLE", "BUNDLE_SHA256", "BUNDLE_VERIFICATION_REPORT")
    announced = all(f"{key}=" in log.read_text(encoding="utf-8") for key in keys)
    if not announced:
        if source_status == "FINAL_VERIFICATION_PASSED":
            raise RuntimeError("passed runtime log lacks portable evidence paths")
        return []
    sources = [_runtime_value(log, key) for key in keys]
    target = run_dir / "runtime"
    target.mkdir(exist_ok=True)
    copied = []
    for source in sources:
        destination = target / source.name
        if destination.exists():
            raise FileExistsError(f"runtime evidence already exists: {destination}")
        shutil.copy2(source, destination)
        copied.append(destination)
    runtime_zip = next(path for path in copied if path.name.endswith(".zip"))
    _sidecar(runtime_zip)
    report = next(path for path in copied if path.name.endswith(".verification.json"))
    payload = _load(report, "runtime verification report")
    if payload.get("status") != "BUNDLE_VERIFIED":
        raise RuntimeError("runtime verification report is not BUNDLE_VERIFIED")
    if source_status == "FINAL_VERIFICATION_PASSED":
        if payload.get("source_status") != "RUNTIME_CERTIFIED":
            raise RuntimeError("passed final run runtime source is not RUNTIME_CERTIFIED")
    if payload.get("zip_sha256") != sha256_file(runtime_zip):
        raise RuntimeError("runtime verification report ZIP digest mismatch")
    return copied


def _verify_handoff(run_dir: Path) -> dict[str, Any]:
    zips = list((run_dir / "handoff").glob("mlforecast-handoff-*.zip"))
    if len(zips) != 1:
        raise RuntimeError("final run must contain one handoff ZIP")
    zip_path = zips[0]
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    result = verify_guarded_handoff(zip_path, sidecar)
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    missing = sorted(REQUIRED_HANDOFF_FILES - names)
    if missing:
        raise RuntimeError(f"handoff omits final-gate files: {missing}")
    return result


def _rewrite_manifest(run_dir: Path) -> tuple[str, str, int]:
    records = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir).as_posix()
        if relative in EXCLUDED:
            continue
        _safe(relative)
        payload = path.read_bytes()
        records.append(
            {
                "path": relative,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = run_dir / "ARTIFACT_MANIFEST.json"
    sums = run_dir / "SHA256SUMS"
    atomic_write_text(
        manifest,
        json.dumps({"format": 2, "artifacts": records}, indent=2, sort_keys=True) + "\n",
    )
    atomic_write_text(
        sums,
        "".join(f"{item['sha256']}  {item['path']}\n" for item in records),
    )
    for item in records:
        path = run_dir.joinpath(*_safe(item["path"]).parts)
        if sha256_file(path) != item["sha256"] or path.stat().st_size != item["size_bytes"]:
            raise RuntimeError(f"final manifest verification failed: {item['path']}")
    return sha256_file(manifest), sha256_file(sums), len(records)


def finalize_final_gate(run_dir: Path) -> dict[str, Any]:
    raw = run_dir.expanduser().absolute()
    if raw.is_symlink() or not raw.is_dir():
        raise RuntimeError(f"invalid final run directory: {raw}")
    root = raw.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"final run contains symlink: {path}")
    report = _load(root / "FINAL_VERIFICATION.json", "FINAL_VERIFICATION.json")
    run_id = report.get("run_id")
    source_status = report.get("status")
    if not isinstance(run_id, str) or RUN_ID.fullmatch(run_id) is None or root.name != run_id:
        raise RuntimeError("invalid final Run ID")
    if source_status not in {
        "FINAL_VERIFICATION_PASSED",
        "FINAL_VERIFICATION_BLOCKED",
        "FINAL_VERIFICATION_FAILED",
        "FINAL_VERIFICATION_PARTIAL",
    }:
        raise RuntimeError("invalid final source status")
    handoff = _verify_handoff(root)
    runtime_files = _copy_runtime(root, source_status)
    manifest_sha, sums_sha, file_count = _rewrite_manifest(root)
    result = {
        "status": "FINAL_GATE_VERIFIED",
        "source_status": source_status,
        "run_id": run_id,
        "run_dir": str(root),
        "handoff_status": handoff.get("status"),
        "runtime_files": [path.name for path in runtime_files],
        "manifest_sha256": manifest_sha,
        "sums_sha256": sums_sha,
        "file_count": file_count,
        "verified_at": datetime.now(UTC).isoformat(),
    }
    atomic_write_text(
        root / "FINAL_GATE_VERIFICATION.json",
        json.dumps(result, indent=2, sort_keys=True) + "\n",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loto-mlforecast-final-gate")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(finalize_final_gate(args.run_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
