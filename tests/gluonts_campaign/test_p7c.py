from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.p7c_analysis import (
    EXPECTED_MODELS,
    P7CInputError,
    build_remediation_plan,
    sha256_file,
    write_remediation_outputs,
)
from loto.adapters.gluonts.p7c_contract import (
    P7CInputIdentity,
    P7CPriority,
    P7CRemediationClass,
    P7CRemediationItem,
    P7CRemediationPlan,
    P7CRerunScope,
    atomic_write_json,
)


def source_identity() -> P7CInputIdentity:
    return P7CInputIdentity(
        p7b_output_directory="/tmp/p7b",
        run_id="run-1",
        commit_sha="a" * 40,
        execution_manifest_sha256="b" * 64,
        execution_checksum_sha256="c" * 64,
        audit_sha256="d" * 64,
        failure_matrix_sha256="e" * 64,
    )


def verified_item(
    lane: str = "compat",
    model: str = "DeepAREstimator",
) -> P7CRemediationItem:
    return P7CRemediationItem(
        item_id=f"{lane}:{model}",
        lane=lane,
        model_class=model,
        current_status="VERIFIED",
        failed_stage="none",
        remediation_class=P7CRemediationClass.VERIFIED,
        priority=P7CPriority.P4,
        rerun_scope=P7CRerunScope.NONE,
        preserve_verified=True,
        action="keep",
        reason="verified",
    )


def test_verified_item_rejects_commands() -> None:
    payload = verified_item().model_dump(mode="json")
    payload["commands"] = ["rerun"]
    with pytest.raises(ValidationError):
        P7CRemediationItem.model_validate(payload)


def test_plan_rejects_false_p8_gate() -> None:
    items = [
        verified_item(lane, model) for lane in ("compat", "latest") for model in EXPECTED_MODELS
    ]
    with pytest.raises(ValidationError):
        P7CRemediationPlan(
            source=source_identity(),
            evidence_state="VALID",
            certification_status="VERIFIED",
            verified_model_lifecycles=18,
            p8_eligible=False,
            items=items,
            recommended_next_action="next",
        )


def test_plan_rejects_duplicate_items() -> None:
    with pytest.raises(ValidationError):
        P7CRemediationPlan(
            source=source_identity(),
            evidence_state="VALID",
            certification_status="FAILED",
            verified_model_lifecycles=2,
            p8_eligible=False,
            items=[verified_item(), verified_item()],
            recommended_next_action="next",
        )


def model_row(lane: str, model: str, category: str | None = None) -> dict:
    verified = category is None
    return {
        "lane": lane,
        "model_class": model,
        "certification_status": "VERIFIED" if verified else "FAILED",
        "failed_stage": "none" if verified else "fit_serialize",
        "failure_category": category,
        "errors": [] if verified else [f"{category} occurred"],
        "fit_status": "VERIFIED" if verified else "FAILED",
        "reload_status": "VERIFIED" if verified else None,
        "artifact_manifest_sha256": ("1" * 64) if verified else None,
        "fit_process_id": 1001 if verified else None,
        "load_process_id": 1002 if verified else None,
    }


def write_sums(root: Path, name: str, excludes: set[str]) -> None:
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in excludes
    ]
    (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_p7b(
    tmp_path: Path,
    *,
    failure: tuple[str, str, str] | None = None,
    evidence_state: str = "VALID",
    certification_status: str | None = None,
) -> Path:
    root = tmp_path / "p7b"
    audit_root = root / "audit"
    audit_root.mkdir(parents=True)
    run_id = "p7b-run"
    commit = "a" * 40
    rows = []
    for lane in ("compat", "latest"):
        for model in EXPECTED_MODELS:
            category = None
            if failure and failure[:2] == (lane, model):
                category = failure[2]
            rows.append(model_row(lane, model, category))
    verified = sum(row["certification_status"] == "VERIFIED" for row in rows)
    status = certification_status or ("VERIFIED" if verified == 18 else "FAILED")
    audit = {
        "schema_version": 1,
        "phase": "P7_TARGET_MACHINE_EXECUTION",
        "run_id": run_id,
        "evidence_state": evidence_state,
        "certification_status": status,
        "verified_model_lifecycles": verified,
        "errors": [] if status == "VERIFIED" else ["not fully verified"],
    }
    matrix = {"schema_version": 1, "run_id": run_id, "rows": rows}
    audit_sha = atomic_write_json(
        audit_root / "p7_target_machine_audit.json",
        audit,
    )
    matrix_sha = atomic_write_json(
        audit_root / "p7_failure_matrix.json",
        matrix,
    )
    atomic_write_json(
        audit_root / "p7_artifact_manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "audit_sha256": audit_sha,
            "failure_matrix_sha256": matrix_sha,
        },
    )
    write_sums(audit_root, "P7_SHA256SUMS", {"P7_SHA256SUMS"})
    journal = {
        "schema_version": 1,
        "phase": "P7B_TARGET_MACHINE_SUPERVISION",
        "run_id": run_id,
        "execution_state": "COMPLETED",
    }
    journal_sha = atomic_write_json(
        root / "p7b_execution_journal.json",
        journal,
    )
    atomic_write_json(
        root / "p7b_execution_manifest.json",
        {
            "schema_version": 1,
            "phase": "P7B_TARGET_MACHINE_SUPERVISION",
            "run_id": run_id,
            "commit_sha": commit,
            "journal_sha256": journal_sha,
        },
    )
    (root / "P7B_EXECUTION_COMPLETE").write_text(
        f"RUN_ID={run_id}\nCOMMIT_SHA={commit}\n",
        encoding="utf-8",
    )
    write_sums(
        root,
        "P7B_EXECUTION_SHA256SUMS",
        {
            "P7B_EXECUTION_SHA256SUMS",
            "P7B_PARTIAL_SHA256SUMS",
            ".p7b.lock",
        },
    )
    return root


def test_verified_run_is_p8_eligible(tmp_path: Path) -> None:
    plan = build_remediation_plan(make_p7b(tmp_path))
    assert plan.p8_eligible
    assert plan.verified_model_lifecycles == 18
    assert all(item.remediation_class is P7CRemediationClass.VERIFIED for item in plan.items)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("VERSION_MISMATCH", P7CRemediationClass.ENVIRONMENT_REPAIR),
        ("FIT_FAILED", P7CRemediationClass.IMPLEMENTATION_REPAIR),
        ("TIMEOUT", P7CRemediationClass.TRANSIENT_RETRY),
        ("UNKNOWN", P7CRemediationClass.MANUAL_TRIAGE),
    ],
)
def test_failure_classification(
    tmp_path: Path,
    category: str,
    expected: P7CRemediationClass,
) -> None:
    root = make_p7b(
        tmp_path,
        failure=("compat", "WaveNetEstimator", category),
    )
    plan = build_remediation_plan(root)
    item = next(item for item in plan.items if item.item_id == "compat:WaveNetEstimator")
    assert item.remediation_class is expected
    assert item.preserve_verified
    assert plan.verified_model_lifecycles == 17
    assert not plan.p8_eligible


def test_invalid_evidence_creates_only_p0_evidence_item(
    tmp_path: Path,
) -> None:
    root = make_p7b(
        tmp_path,
        evidence_state="INVALID",
        certification_status="NOT_EVALUATED",
    )
    plan = build_remediation_plan(root)
    assert len(plan.items) == 1
    assert plan.items[0].remediation_class is P7CRemediationClass.EVIDENCE_REPAIR
    assert plan.items[0].priority is P7CPriority.P0
    assert plan.verified_model_lifecycles == 0


def test_tampered_input_is_rejected(tmp_path: Path) -> None:
    root = make_p7b(tmp_path)
    path = root / "audit/p7_failure_matrix.json"
    path.write_text(path.read_text() + " ", encoding="utf-8")
    with pytest.raises(P7CInputError, match="checksum mismatch"):
        build_remediation_plan(root)


def test_valid_evidence_requires_exactly_18_rows(tmp_path: Path) -> None:
    root = make_p7b(tmp_path)
    matrix_path = root / "audit/p7_failure_matrix.json"
    matrix = json.loads(matrix_path.read_text())
    matrix["rows"].pop()
    matrix_sha = atomic_write_json(matrix_path, matrix)
    manifest_path = root / "audit/p7_artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["failure_matrix_sha256"] = matrix_sha
    atomic_write_json(manifest_path, manifest)
    write_sums(root / "audit", "P7_SHA256SUMS", {"P7_SHA256SUMS"})
    write_sums(
        root,
        "P7B_EXECUTION_SHA256SUMS",
        {
            "P7B_EXECUTION_SHA256SUMS",
            "P7B_PARTIAL_SHA256SUMS",
            ".p7b.lock",
        },
    )
    with pytest.raises(P7CInputError, match="18 unique"):
        build_remediation_plan(root)


def test_audit_verified_count_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    root = make_p7b(tmp_path)
    audit_path = root / "audit/p7_target_machine_audit.json"
    audit = json.loads(audit_path.read_text())
    audit["verified_model_lifecycles"] = 17
    audit_sha = atomic_write_json(audit_path, audit)
    manifest_path = root / "audit/p7_artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["audit_sha256"] = audit_sha
    atomic_write_json(manifest_path, manifest)
    write_sums(root / "audit", "P7_SHA256SUMS", {"P7_SHA256SUMS"})
    write_sums(
        root,
        "P7B_EXECUTION_SHA256SUMS",
        {
            "P7B_EXECUTION_SHA256SUMS",
            "P7B_PARTIAL_SHA256SUMS",
            ".p7b.lock",
        },
    )
    with pytest.raises(P7CInputError, match="verified lifecycle count"):
        build_remediation_plan(root)


def test_nonempty_output_is_rejected(tmp_path: Path) -> None:
    root = make_p7b(tmp_path)
    plan = build_remediation_plan(root)
    output = tmp_path / "existing-output"
    output.mkdir()
    (output / "existing.txt").write_text("do not overwrite")
    with pytest.raises(ValueError, match="absent or empty"):
        write_remediation_outputs(root, output, plan)


def test_output_must_be_outside_p7b_root(tmp_path: Path) -> None:
    root = make_p7b(tmp_path)
    plan = build_remediation_plan(root)
    with pytest.raises(ValueError, match="must not be inside"):
        write_remediation_outputs(root, root / "p7c", plan)


def test_outputs_are_hashed_and_do_not_modify_input(
    tmp_path: Path,
) -> None:
    root = make_p7b(
        tmp_path,
        failure=("latest", "LagTSTEstimator", "FIT_FAILED"),
    )
    before = sha256_file(root / "P7B_EXECUTION_SHA256SUMS")
    plan = build_remediation_plan(root)
    output = tmp_path / "p7c"
    identities = write_remediation_outputs(root, output, plan)
    assert set(identities) == {
        "plan_sha256",
        "queue_sha256",
        "report_sha256",
        "manifest_sha256",
        "checksums_sha256",
    }
    assert (output / "P7C_SHA256SUMS").is_file()
    assert sha256_file(root / "P7B_EXECUTION_SHA256SUMS") == before
