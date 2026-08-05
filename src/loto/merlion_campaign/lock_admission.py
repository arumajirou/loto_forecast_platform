from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from loto.merlion_campaign.bootstrap_evidence_verify import verify_bootstrap_evidence_zip
from loto.merlion_campaign.git_provenance import (
    parse_git_porcelain_z,
    probe_git_state,
    validate_git_provenance,
)
from loto.merlion_campaign.license_review import (
    canonical_sha256,
    parse_dependency_inventory,
    validate_license_review,
)

ADMISSION_SCHEMA = "merlion-lock-admission-v1"
ALLOWED_LOCK_PATH = "environments/merlion-core-py311/uv.lock"
EVIDENCE_LOCK_PATH = "environment/uv.lock"
EVIDENCE_AUDIT_PATH = "run/DEPENDENCY_AUDIT.json"
EVIDENCE_INVENTORY_PATH = "run/DEPENDENCY_INVENTORY.csv"
EVIDENCE_GIT_PATH = "run/GIT_PROVENANCE.json"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.replace(path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json_object(data: bytes, *, label: str) -> dict[str, Any]:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def read_evidence_payloads(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        names = {info.filename for info in archive.infolist()}
        required = {
            EVIDENCE_LOCK_PATH,
            EVIDENCE_AUDIT_PATH,
            EVIDENCE_INVENTORY_PATH,
            EVIDENCE_GIT_PATH,
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"evidence ZIP is missing admission files: {missing}")
        return {name: archive.read(name) for name in required}


def _scope_blockers(changes: Sequence[Mapping[str, str]]) -> list[str]:
    blockers: list[str] = []
    lock_seen = False
    for change in changes:
        path = str(change.get("path", ""))
        source = str(change.get("source_path", ""))
        if path != ALLOWED_LOCK_PATH or source:
            blockers.append(f"GIT_SCOPE_VIOLATION:{source or path}")
            continue
        lock_seen = True
        status = str(change.get("status", ""))
        if status == "!!" or "D" in status:
            blockers.append(f"LOCK_GIT_STATUS_INVALID:{status}")
    if not lock_seen:
        blockers.append("LOCK_NOT_PRESENT_IN_GIT_DIFF")
    return blockers


def evaluate_lock_admission(
    root: Path,
    evidence_zip: Path,
    license_review: Path,
    *,
    expected_head: str,
    evidence_verifier: Callable[[Path], Mapping[str, Any]] = verify_bootstrap_evidence_zip,
    git_probe: Callable[[Path], Mapping[str, Any]] = probe_git_state,
) -> dict[str, Any]:
    root = root.resolve()
    evidence_zip = evidence_zip.resolve()
    license_review = license_review.resolve()
    blockers: list[str] = []
    if len(expected_head) != 40 or any(value not in "0123456789abcdef" for value in expected_head):
        blockers.append("EXPECTED_HEAD_INVALID")

    evidence_result = dict(evidence_verifier(evidence_zip))
    if evidence_result.get("status") != "PASS":
        blockers.append("EVIDENCE_VERIFICATION_NOT_PASS")
    if evidence_result.get("evidence_status") != "BOOTSTRAP_PASS":
        blockers.append("EVIDENCE_STATUS_NOT_BOOTSTRAP_PASS")
    evidence_zip_sha256 = _sha256_bytes(evidence_zip.read_bytes())
    if evidence_result.get("zip_sha256") != evidence_zip_sha256:
        blockers.append("EVIDENCE_ZIP_HASH_MISMATCH")

    payloads = read_evidence_payloads(evidence_zip)
    git_provenance = _read_json_object(
        payloads[EVIDENCE_GIT_PATH],
        label="GIT_PROVENANCE.json",
    )
    validate_git_provenance(git_provenance, require_clean=True)
    provenance_head = git_provenance.get("head_sha")
    if provenance_head != expected_head:
        blockers.append("EVIDENCE_GIT_HEAD_MISMATCH")

    embedded_lock = payloads[EVIDENCE_LOCK_PATH]
    lock_sha256 = _sha256_bytes(embedded_lock)
    workspace_lock = root / ALLOWED_LOCK_PATH
    if not workspace_lock.is_file() or workspace_lock.is_symlink():
        blockers.append("WORKSPACE_LOCK_MISSING_OR_UNSAFE")
        workspace_lock_sha256 = None
    else:
        workspace_lock_sha256 = _sha256_bytes(workspace_lock.read_bytes())
        if workspace_lock_sha256 != lock_sha256:
            blockers.append("WORKSPACE_LOCK_HASH_MISMATCH")

    audit = _read_json_object(payloads[EVIDENCE_AUDIT_PATH], label="DEPENDENCY_AUDIT.json")
    if audit.get("status") != "PASS":
        blockers.append("DEPENDENCY_AUDIT_NOT_PASS")
    if audit.get("lock_sha256") != lock_sha256:
        blockers.append("DEPENDENCY_AUDIT_LOCK_HASH_MISMATCH")
    inventory_rows = parse_dependency_inventory(payloads[EVIDENCE_INVENTORY_PATH])
    registry_inventory_count = sum(row.get("source_kind") == "registry" for row in inventory_rows)
    if audit.get("package_count") not in {None, len(inventory_rows)}:
        blockers.append("DEPENDENCY_AUDIT_PACKAGE_COUNT_MISMATCH")
    if audit.get("registry_package_count") not in {None, registry_inventory_count}:
        blockers.append("DEPENDENCY_AUDIT_REGISTRY_COUNT_MISMATCH")

    if not license_review.is_file() or license_review.is_symlink():
        blockers.append("LICENSE_REVIEW_MISSING_OR_UNSAFE")
        review: dict[str, Any] = {}
        license_review_bytes = b""
    else:
        license_review_bytes = license_review.read_bytes()
        loaded_review = json.loads(license_review_bytes)
        if not isinstance(loaded_review, dict):
            raise ValueError("license review must be a JSON object")
        review = loaded_review
    review_blockers, registry_count = validate_license_review(
        review,
        inventory_rows,
        evidence_zip_sha256=evidence_zip_sha256,
        lock_sha256=lock_sha256,
    )
    blockers.extend(review_blockers)

    git_state = dict(git_probe(root))
    if git_state.get("head_sha") != expected_head:
        blockers.append("GIT_HEAD_MISMATCH")
    if git_state.get("head_sha") != provenance_head:
        blockers.append("WORKSPACE_AND_EVIDENCE_HEAD_MISMATCH")
    changes = git_state.get("changes")
    if not isinstance(changes, list):
        blockers.append("GIT_CHANGES_INVALID")
        changes = []
    blockers.extend(_scope_blockers(changes))

    report: dict[str, Any] = {
        "schema_version": ADMISSION_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "ADMITTED" if not blockers else "BLOCKED",
        "expected_head": expected_head,
        "actual_head": git_state.get("head_sha"),
        "evidence_head": provenance_head,
        "evidence_branch": git_provenance.get("branch"),
        "evidence_zip": str(evidence_zip),
        "evidence_zip_sha256": evidence_zip_sha256,
        "evidence_manifest_sha256": evidence_result.get("manifest_sha256"),
        "lock_path": ALLOWED_LOCK_PATH,
        "lock_sha256": lock_sha256,
        "workspace_lock_sha256": workspace_lock_sha256,
        "dependency_package_count": len(inventory_rows),
        "registry_package_count": registry_count,
        "license_review_sha256": _sha256_bytes(license_review_bytes),
        "git_changes": changes,
        "blockers": sorted(set(blockers)),
        "next_action": (
            "commit the isolated uv.lock in a separate intentional commit"
            if not blockers
            else "resolve every blocker and create a new admission report"
        ),
    }
    report["report_sha256"] = canonical_sha256(report)
    return report


def render_admission_decision(report: Mapping[str, Any]) -> str:
    status = str(report.get("status", "BLOCKED"))
    blockers = report.get("blockers", [])
    blocker_lines = "\n".join(f"- `{value}`" for value in blockers) or "- None"
    return (
        "# Merlion Lock Admission Decision\n\n"
        f"Status: `{status}`\n\n"
        f"Expected HEAD: `{report.get('expected_head')}`\n\n"
        f"Actual HEAD: `{report.get('actual_head')}`\n\n"
        f"Lock SHA-256: `{report.get('lock_sha256')}`\n\n"
        f"Evidence ZIP SHA-256: `{report.get('evidence_zip_sha256')}`\n\n"
        "## Blockers\n\n"
        f"{blocker_lines}\n\n"
        "## Next action\n\n"
        f"{report.get('next_action')}\n"
    )
