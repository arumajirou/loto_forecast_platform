from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from loto.merlion_campaign.bootstrap_resume import (
    PLAN_SCHEMA,
    PREFLIGHT_SCHEMA,
    _validate_hash_bound_payload,
)
from loto.merlion_campaign.git_provenance import validate_git_provenance

EVIDENCE_SCHEMA = "merlion-bootstrap-evidence-v1"
MANIFEST_NAME = "BOOTSTRAP_EVIDENCE_MANIFEST.json"
SHA256SUMS_NAME = "SHA256SUMS"
RUN_ALLOWLIST = (
    "PREFLIGHT.json",
    "GIT_PROVENANCE.json",
    "BOOTSTRAP_PLAN.json",
    "PYTHON_PROVISION.log",
    "PYTHON_PATH.txt",
    "bootstrap.log",
    "DEPENDENCY_AUDIT.json",
    "DEPENDENCY_INVENTORY.csv",
    "dependency-sha256.txt",
    "BOOTSTRAP_FAILURE.json",
    "exit_code",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_archive_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts:
        raise ValueError("archive path must be relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("archive path is unsafe")
    return path.as_posix()


def read_exit_code(run_dir: Path) -> int:
    value = (run_dir / "exit_code").read_text(encoding="utf-8").strip()
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("bootstrap exit_code is invalid") from exc


def collect_evidence_files(run_dir: Path, env_dir: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for filename in RUN_ALLOWLIST:
        source = run_dir / filename
        if source.is_symlink():
            raise ValueError(f"evidence source is a symlink: {filename}")
        if source.is_file():
            files[f"run/{filename}"] = source.read_bytes()
    for filename in ("pyproject.toml", "uv.lock"):
        source = env_dir / filename
        if source.is_symlink():
            raise ValueError(f"environment source is a symlink: {filename}")
        if source.is_file():
            files[f"environment/{filename}"] = source.read_bytes()
    return files


def validate_json_mapping(data: bytes, *, label: str) -> dict[str, Any]:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def validate_run_evidence(
    files: Mapping[str, bytes],
    *,
    exit_code: int,
    run_id: str,
) -> str:
    preflight = validate_json_mapping(files["run/PREFLIGHT.json"], label="PREFLIGHT.json")
    if preflight.get("schema_version") == PREFLIGHT_SCHEMA:
        _validate_hash_bound_payload(preflight, hash_field="report_sha256")

    provenance = validate_json_mapping(
        files["run/GIT_PROVENANCE.json"],
        label="GIT_PROVENANCE.json",
    )
    validate_git_provenance(provenance, require_clean=exit_code == 0)

    plan_data = files.get("run/BOOTSTRAP_PLAN.json")
    if plan_data is not None:
        plan = validate_json_mapping(plan_data, label="BOOTSTRAP_PLAN.json")
        if plan.get("schema_version") != PLAN_SCHEMA:
            raise ValueError("unsupported bootstrap plan schema")
        _validate_hash_bound_payload(plan, hash_field="plan_sha256")
        preflight_hash = preflight.get("report_sha256")
        if preflight_hash and plan.get("preflight_report_sha256") != preflight_hash:
            raise ValueError("bootstrap plan preflight hash mismatch")

    has_failure = "run/BOOTSTRAP_FAILURE.json" in files
    has_lock = "environment/uv.lock" in files
    has_audit = "run/DEPENDENCY_AUDIT.json" in files
    if exit_code == 0:
        if has_failure:
            raise ValueError("successful bootstrap contains failure evidence")
        if not has_lock or not has_audit:
            raise ValueError("successful bootstrap is missing lock or dependency audit")
        audit = validate_json_mapping(
            files["run/DEPENDENCY_AUDIT.json"],
            label="DEPENDENCY_AUDIT.json",
        )
        if audit.get("status") != "PASS":
            raise ValueError("successful bootstrap dependency audit is not PASS")
        return "BOOTSTRAP_PASS"

    if not has_failure:
        raise ValueError("blocked bootstrap is missing BOOTSTRAP_FAILURE.json")
    failure = validate_json_mapping(
        files["run/BOOTSTRAP_FAILURE.json"],
        label="BOOTSTRAP_FAILURE.json",
    )
    if failure.get("status") != "BLOCKED":
        raise ValueError("bootstrap failure status is invalid")
    if failure.get("run_id") != run_id:
        raise ValueError("bootstrap failure run_id mismatch")
    if failure.get("exit_code") != exit_code:
        raise ValueError("bootstrap failure exit_code mismatch")
    return "BOOTSTRAP_BLOCKED"
