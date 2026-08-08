from __future__ import annotations

from pathlib import Path
from typing import Any

from .p7d_common import (
    P7DBundleError,
    _marker_values,
    _read_json,
    _read_return_code,
    sha256_file,
    verify_checksum_inventory,
)


def _verify_p7b(p7b_root: Path) -> dict[str, Any]:
    required = (
        "P7B_EXECUTION_COMPLETE",
        "P7B_EXECUTION_SHA256SUMS",
        "p7b_execution_manifest.json",
        "p7b_execution_journal.json",
        "audit/P7_SHA256SUMS",
        "audit/p7_target_machine_audit.json",
        "audit/p7_failure_matrix.json",
    )
    missing = [name for name in required if not (p7b_root / name).is_file()]
    if missing:
        raise P7DBundleError(f"missing P7B files: {missing}")
    execution_checksum_sha = verify_checksum_inventory(
        p7b_root,
        "P7B_EXECUTION_SHA256SUMS",
        excluded_names={"P7B_PARTIAL_SHA256SUMS", ".p7b.lock"},
    )
    verify_checksum_inventory(p7b_root / "audit", "P7_SHA256SUMS")
    marker = _marker_values(p7b_root / "P7B_EXECUTION_COMPLETE")
    manifest_path = p7b_root / "p7b_execution_manifest.json"
    journal_path = p7b_root / "p7b_execution_journal.json"
    manifest = _read_json(manifest_path)
    journal = _read_json(journal_path)
    if manifest.get("run_id") != marker["RUN_ID"]:
        raise P7DBundleError("P7B run ID mismatch")
    if manifest.get("commit_sha") != marker["COMMIT_SHA"]:
        raise P7DBundleError("P7B commit SHA mismatch")
    if manifest.get("journal_sha256") != sha256_file(journal_path):
        raise P7DBundleError("P7B journal SHA-256 mismatch")
    if journal.get("execution_state") != "COMPLETED":
        raise P7DBundleError("P7B journal is not COMPLETED")
    if journal.get("run_id") != marker["RUN_ID"]:
        raise P7DBundleError("P7B journal run ID mismatch")
    audit_path = p7b_root / "audit/p7_target_machine_audit.json"
    matrix_path = p7b_root / "audit/p7_failure_matrix.json"
    return {
        "run_id": marker["RUN_ID"],
        "commit_sha": marker["COMMIT_SHA"],
        "execution_manifest_sha256": sha256_file(manifest_path),
        "execution_checksum_sha256": execution_checksum_sha,
        "audit_sha256": sha256_file(audit_path),
        "failure_matrix_sha256": sha256_file(matrix_path),
    }


def _verify_p7c(p7c_root: Path, p7b: dict[str, Any]) -> dict[str, Any]:
    required = (
        "P7C_SHA256SUMS",
        "p7c_remediation_plan.json",
        "p7c_remediation_queue.tsv",
        "p7c_remediation_report.md",
        "p7c_artifact_manifest.json",
    )
    missing = [name for name in required if not (p7c_root / name).is_file()]
    if missing:
        raise P7DBundleError(f"missing P7C files: {missing}")
    checksum_sha = verify_checksum_inventory(p7c_root, "P7C_SHA256SUMS")
    plan_path = p7c_root / "p7c_remediation_plan.json"
    manifest_path = p7c_root / "p7c_artifact_manifest.json"
    queue_path = p7c_root / "p7c_remediation_queue.tsv"
    report_path = p7c_root / "p7c_remediation_report.md"
    plan = _read_json(plan_path)
    manifest = _read_json(manifest_path)
    source = plan.get("source")
    if not isinstance(source, dict):
        raise P7DBundleError("P7C plan source identity is missing")
    expected = {
        "run_id": p7b["run_id"],
        "source_commit_sha": p7b["commit_sha"],
        "source_execution_manifest_sha256": p7b["execution_manifest_sha256"],
        "source_execution_checksum_sha256": p7b["execution_checksum_sha256"],
        "source_audit_sha256": p7b["audit_sha256"],
        "source_failure_matrix_sha256": p7b["failure_matrix_sha256"],
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise P7DBundleError(f"P7C manifest identity mismatch: {key}")
    plan_expected = {
        "run_id": p7b["run_id"],
        "commit_sha": p7b["commit_sha"],
        "execution_manifest_sha256": p7b["execution_manifest_sha256"],
        "execution_checksum_sha256": p7b["execution_checksum_sha256"],
        "audit_sha256": p7b["audit_sha256"],
        "failure_matrix_sha256": p7b["failure_matrix_sha256"],
    }
    for key, value in plan_expected.items():
        if source.get(key) != value:
            raise P7DBundleError(f"P7C plan identity mismatch: {key}")
    file_hashes = {
        "plan_sha256": sha256_file(plan_path),
        "queue_sha256": sha256_file(queue_path),
        "report_sha256": sha256_file(report_path),
    }
    for key, value in file_hashes.items():
        if manifest.get(key) != value:
            raise P7DBundleError(f"P7C artifact hash mismatch: {key}")
    if manifest.get("p8_eligible") != plan.get("p8_eligible"):
        raise P7DBundleError("P7C manifest and plan P8 status mismatch")
    verified = plan.get("verified_model_lifecycles")
    if not isinstance(verified, int) or not 0 <= verified <= 18:
        raise P7DBundleError("invalid P7C verified lifecycle count")
    return {
        "manifest_sha256": sha256_file(manifest_path),
        "checksum_sha256": checksum_sha,
        "evidence_state": str(plan.get("evidence_state", "")),
        "certification_status": str(plan.get("certification_status", "")),
        "verified_model_lifecycles": verified,
        "p8_eligible": bool(plan.get("p8_eligible")),
    }


def verify_run_root(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    required = (
        "RUN_ID",
        "p7b.rc",
        "p7c.rc",
        "P7C_ORCHESTRATION_SHA256SUMS",
    )
    missing = [name for name in required if not (run_root / name).is_file()]
    if missing or not (run_root / "p7b").is_dir() or not (run_root / "p7c").is_dir():
        raise P7DBundleError(f"incomplete P7C orchestration root: {missing}")
    orchestration_sha = verify_checksum_inventory(
        run_root,
        "P7C_ORCHESTRATION_SHA256SUMS",
    )
    run_id = (run_root / "RUN_ID").read_text("utf-8").strip()
    p7b_rc = _read_return_code(run_root / "p7b.rc")
    p7c_rc = _read_return_code(run_root / "p7c.rc")
    if p7c_rc not in {0, 10, 20}:
        raise P7DBundleError(f"P7C did not produce a handoff state: rc={p7c_rc}")
    p7b = _verify_p7b(run_root / "p7b")
    p7c = _verify_p7c(run_root / "p7c", p7b)
    if run_id != p7b["run_id"]:
        raise P7DBundleError("orchestration and P7B run IDs differ")
    if p7c_rc == 0 and not p7c["p8_eligible"]:
        raise P7DBundleError("P7C rc=0 requires p8_eligible=true")
    if p7c_rc != 0 and p7c["p8_eligible"]:
        raise P7DBundleError("nonzero P7C rc cannot be P8 eligible")
    if p7c_rc == 10 and p7c["evidence_state"] != "VALID":
        raise P7DBundleError("P7C rc=10 requires VALID evidence")
    if p7c_rc == 20 and p7c["evidence_state"] == "VALID":
        raise P7DBundleError("P7C rc=20 requires invalid or incomplete evidence")
    if p7c["p8_eligible"]:
        gate = (
            p7c["evidence_state"] == "VALID"
            and p7c["certification_status"] == "VERIFIED"
            and p7c["verified_model_lifecycles"] == 18
        )
        if not gate:
            raise P7DBundleError("P7C P8 gate is inconsistent")
    return {
        **p7b,
        **p7c,
        "p7b_return_code": p7b_rc,
        "p7c_return_code": p7c_rc,
        "orchestration_checksum_sha256": orchestration_sha,
    }
