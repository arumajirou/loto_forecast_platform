from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from loto.merlion_campaign.bootstrap_evidence_contract import (
    EVIDENCE_SCHEMA,
    MANIFEST_NAME,
    SHA256SUMS_NAME,
    collect_evidence_files,
    read_exit_code,
    safe_archive_name,
    sha256_bytes,
    validate_run_evidence,
)
from loto.merlion_campaign.bootstrap_resume import _canonical_sha256, atomic_write_text


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(safe_archive_name(name), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def package_bootstrap_evidence(
    run_dir: Path,
    env_dir: Path,
    destination: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    env_dir = env_dir.resolve()
    destination = destination.resolve()
    sidecar = destination.with_suffix(destination.suffix + ".sha256")
    if destination.exists() or sidecar.exists():
        raise ValueError("bootstrap evidence output already exists")
    if not (run_dir / "PREFLIGHT.json").is_file():
        raise ValueError("PREFLIGHT.json is required")
    if not (run_dir / "exit_code").is_file():
        raise ValueError("exit_code is required")

    files = collect_evidence_files(run_dir, env_dir)
    exit_code = read_exit_code(run_dir)
    status = validate_run_evidence(files, exit_code=exit_code, run_id=run_id)
    records = [
        {"path": name, "bytes": len(data), "sha256": sha256_bytes(data)}
        for name, data in sorted(files.items())
    ]
    manifest: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "status": status,
        "run_id": run_id,
        "exit_code": exit_code,
        "files": records,
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    sums_rows = [f"{record['sha256']}  {record['path']}" for record in records]
    sums_rows.append(f"{sha256_bytes(manifest_bytes)}  {MANIFEST_NAME}")
    sums_bytes = ("\n".join(sums_rows) + "\n").encode("utf-8")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w+b",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name, data in sorted(files.items()):
                archive.writestr(_zip_info(name), data)
            archive.writestr(_zip_info(MANIFEST_NAME), manifest_bytes)
            archive.writestr(_zip_info(SHA256SUMS_NAME), sums_bytes)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    zip_sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    atomic_write_text(sidecar, zip_sha + "\n")
    return {
        "status": status,
        "zip_path": str(destination),
        "zip_sha256": zip_sha,
        "file_count": len(files) + 2,
        "manifest_sha256": manifest["manifest_sha256"],
    }
