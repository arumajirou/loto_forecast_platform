"""Offline integrity verification for registry reconciliation evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .persistence import sha256_file, verify_sha256s
from .prospective_registry import verify_prospective_registry
from .prospective_registry_contract import _canonical_sha256, _read_json
from .prospective_registry_reconciliation_contract import (
    MLFLOW_SNAPSHOT,
    POSTGRES_SNAPSHOT,
    RECONCILIATION_EXPECTED,
    RECONCILIATION_MANIFEST,
    RECONCILIATION_REPORT,
    RECONCILIATION_SCHEMA_VERSION,
)


def _reconciliation_inventory(root: Path) -> list[dict[str, Any]]:
    excluded = {RECONCILIATION_MANIFEST, "SHA256SUMS"}
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix(),
        )
        if path.relative_to(root).as_posix() not in excluded
    ]


def _reject_symlinks(root: Path) -> list[str]:
    if root.is_symlink() or not root.is_dir():
        return [f"reconciliation artifact is not a regular directory: {root}"]
    return [
        f"reconciliation artifact contains symlink: {path.relative_to(root).as_posix()}"
        for path in root.rglob("*")
        if path.is_symlink()
    ]


def verify_registry_reconciliation(root: Path) -> dict[str, Any]:
    """Verify reconciliation evidence without contacting either backend."""

    root = root.resolve()
    failures = _reject_symlinks(root)
    failures.extend(f"SHA256SUMS:{item}" for item in verify_sha256s(root))
    try:
        expected = _read_json(
            root / RECONCILIATION_EXPECTED,
            "reconciliation expected snapshot",
        )
        postgres = _read_json(
            root / POSTGRES_SNAPSHOT,
            "PostgreSQL snapshot",
        )
        mlflow = _read_json(root / MLFLOW_SNAPSHOT, "MLflow snapshot")
        report = _read_json(root / RECONCILIATION_REPORT, "reconciliation report")
        manifest = _read_json(
            root / RECONCILIATION_MANIFEST,
            "reconciliation manifest",
        )
    except ValueError as exc:
        failures.append(str(exc))
        return {
            "status": "FAIL",
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "failures": failures,
        }
    expected_core = {key: value for key, value in expected.items() if key != "expected_sha256"}
    if expected.get("expected_sha256") != _canonical_sha256(expected_core):
        failures.append("expected snapshot canonical SHA-256 mismatch")
    manifest_core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != _canonical_sha256(manifest_core):
        failures.append("reconciliation manifest canonical SHA-256 mismatch")
    if manifest.get("files") != _reconciliation_inventory(root):
        failures.append("reconciliation manifest file inventory mismatch")
    identities = {
        str(value)
        for value in (
            expected.get("registry_id"),
            report.get("registry_id"),
            manifest.get("registry_id"),
        )
        if str(value or "").strip()
    }
    if len(identities) != 1:
        failures.append("reconciliation registry_id is missing or inconsistent")
    if manifest.get("expected_sha256") != sha256_file(root / RECONCILIATION_EXPECTED):
        failures.append("expected snapshot file SHA mismatch")
    if manifest.get("postgres_snapshot_sha256") != sha256_file(root / POSTGRES_SNAPSHOT):
        failures.append("PostgreSQL snapshot file SHA mismatch")
    if manifest.get("mlflow_snapshot_sha256") != sha256_file(root / MLFLOW_SNAPSHOT):
        failures.append("MLflow snapshot file SHA mismatch")
    if manifest.get("report_sha256") != sha256_file(root / RECONCILIATION_REPORT):
        failures.append("reconciliation report file SHA mismatch")
    if report.get("safety", {}).get("read_only_backend_access") is not True:
        failures.append("reconciliation safety must state read-only backend access")
    if report.get("safety", {}).get("automatic_repair") is not False:
        failures.append("reconciliation artifact permits automatic repair")
    if report.get("safety", {}).get("secrets_persisted") is not False:
        failures.append("reconciliation artifact may persist secrets")

    operational_status = str(report.get("status") or "")
    if operational_status == "PASS":
        if report.get("drift_failures") or report.get("backend_errors"):
            failures.append("PASS reconciliation contains failures")
        if postgres.get("status") != "PASS" or mlflow.get("status") != "PASS":
            failures.append("PASS reconciliation lacks PASS backend snapshots")
    elif operational_status == "DRIFT":
        if not report.get("drift_failures") or report.get("backend_errors"):
            failures.append("DRIFT reconciliation evidence is inconsistent")
    elif operational_status == "BLOCKED":
        if not report.get("backend_errors"):
            failures.append("BLOCKED reconciliation lacks backend errors")
    else:
        failures.append(f"unsupported reconciliation operational status: {operational_status}")

    source_receipt = root / "source_receipt"
    source_status = "NOT_AVAILABLE"
    if source_receipt.is_dir():
        source_result = verify_prospective_registry(source_receipt)
        source_status = str(source_result.get("status") or "FAIL")
        if source_status != "PASS":
            failures.append("copied source registry receipt verification failed")
        source_files = {
            path.relative_to(source_receipt).as_posix(): sha256_file(path)
            for path in source_receipt.rglob("*")
            if path.is_file()
        }
        expected_tree = report.get("source_receipt", {}).get("tree_sha256")
        if expected_tree != _canonical_sha256(source_files):
            failures.append("copied source registry receipt tree hash mismatch")
    else:
        failures.append("copied source registry receipt is missing")

    return {
        "status": "PASS" if not failures else "FAIL",
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "operational_status": operational_status,
        "registry_id": expected.get("registry_id"),
        "source_receipt_verification": source_status,
        "failures": failures,
    }
