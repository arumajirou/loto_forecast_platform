from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .p7c_contract import (
    P7CInputIdentity,
    P7CPriority,
    P7CRemediationClass,
    P7CRemediationItem,
    P7CRemediationPlan,
    P7CRerunScope,
    atomic_write_json,
)

EXPECTED_MODELS = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)

EVIDENCE_FAILURES = {
    "BOOTSTRAP_FAILED",
    "MISSING_ARTIFACT",
    "CHECKSUM_MISMATCH",
    "CHECKSUM_INVENTORY_MISMATCH",
    "MANIFEST_MISMATCH",
    "PROVENANCE_MISMATCH",
    "LOCKFILE_MISMATCH",
    "REGISTRY_MISMATCH",
    "MODEL_SET_MISMATCH",
}
ENVIRONMENT_FAILURES = {
    "VERSION_MISMATCH",
    "IMPORT_FAILED",
}
IMPLEMENTATION_FAILURES = {
    "MODEL_UNSUPPORTED",
    "DISTRIBUTION_UNSUPPORTED",
    "SIGNATURE_MISMATCH",
    "UNSUPPORTED_ARGUMENT",
    "RESOURCE_POLICY_VIOLATION",
    "CONSTRUCTOR_FAILED",
    "DATASET_FAILED",
    "FIT_FAILED",
    "PREDICT_FAILED",
    "OUTPUT_SHAPE_FAILED",
    "NON_FINITE_OUTPUT",
    "DEVICE_MISMATCH",
    "SERIALIZE_FAILED",
    "ARTIFACT_INTEGRITY_FAILED",
    "PROCESS_RESTART_REQUIRED",
    "DESERIALIZE_FAILED",
    "IDENTITY_MISMATCH",
}
TRANSIENT_FAILURES = {"PROVIDER_CRASH", "TIMEOUT"}


class P7CInputError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise P7CInputError(
            f"failed to read JSON {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise P7CInputError(f"JSON root must be an object: {path}")
    return payload


def _safe_checksum_path(root: Path, token: str) -> Path:
    candidate = (root / token).resolve()
    root_resolved = root.resolve()
    if candidate == root_resolved or root_resolved not in candidate.parents:
        raise P7CInputError(f"checksum path escapes input root: {token}")
    return candidate


def verify_checksum_inventory(root: Path, checksum_name: str) -> str:
    checksum_path = root / checksum_name
    if not checksum_path.is_file():
        raise P7CInputError(f"missing checksum file: {checksum_path}")
    entries: dict[Path, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text("utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise P7CInputError(
                f"invalid checksum line {line_number}: {checksum_name}"
            )
        digest, token = parts
        path = _safe_checksum_path(root, token.strip().lstrip("*"))
        if path in entries:
            raise P7CInputError(f"duplicate checksum path: {token}")
        entries[path] = digest.lower()
    excluded = {
        checksum_name,
        "P7B_PARTIAL_SHA256SUMS",
        ".p7b.lock",
    }
    if checksum_name == "P7B_EXECUTION_SHA256SUMS":
        excluded.add("P7B_EXECUTION_SHA256SUMS")
    observed = {
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.name not in excluded
    }
    if set(entries) != observed:
        missing = sorted(
            str(path.relative_to(root)) for path in observed - set(entries)
        )
        stale = sorted(
            str(path.relative_to(root)) for path in set(entries) - observed
        )
        raise P7CInputError(
            f"checksum inventory mismatch for {checksum_name}: "
            f"missing={missing}, stale={stale}"
        )
    for path, expected in entries.items():
        if not path.is_file() or sha256_file(path) != expected:
            raise P7CInputError(f"checksum mismatch: {path.relative_to(root)}")
    return sha256_file(checksum_path)


def _completion_marker(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    if not values.get("RUN_ID") or not values.get("COMMIT_SHA"):
        raise P7CInputError("P7B_EXECUTION_COMPLETE is incomplete")
    return values


def verify_p7b_input(
    root: Path,
) -> tuple[P7CInputIdentity, dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    required = (
        "P7B_EXECUTION_COMPLETE",
        "P7B_EXECUTION_SHA256SUMS",
        "p7b_execution_manifest.json",
        "p7b_execution_journal.json",
        "audit/p7_target_machine_audit.json",
        "audit/p7_failure_matrix.json",
        "audit/p7_artifact_manifest.json",
        "audit/P7_SHA256SUMS",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise P7CInputError(f"missing required P7B artifacts: {missing}")
    execution_checksum_sha = verify_checksum_inventory(
        root,
        "P7B_EXECUTION_SHA256SUMS",
    )
    marker = _completion_marker(root / "P7B_EXECUTION_COMPLETE")
    execution_manifest_path = root / "p7b_execution_manifest.json"
    journal_path = root / "p7b_execution_journal.json"
    execution_manifest = _load_json(execution_manifest_path)
    journal = _load_json(journal_path)
    if execution_manifest.get("run_id") != marker["RUN_ID"]:
        raise P7CInputError("P7B run ID mismatch")
    if execution_manifest.get("commit_sha") != marker["COMMIT_SHA"]:
        raise P7CInputError("P7B commit SHA mismatch")
    if execution_manifest.get("journal_sha256") != sha256_file(journal_path):
        raise P7CInputError("P7B journal SHA-256 mismatch")
    if journal.get("execution_state") != "COMPLETED":
        raise P7CInputError("P7B execution journal is not COMPLETED")
    if journal.get("run_id") != marker["RUN_ID"]:
        raise P7CInputError("P7B journal run ID mismatch")

    audit_root = root / "audit"
    verify_checksum_inventory(audit_root, "P7_SHA256SUMS")
    audit_path = audit_root / "p7_target_machine_audit.json"
    matrix_path = audit_root / "p7_failure_matrix.json"
    audit_manifest = _load_json(audit_root / "p7_artifact_manifest.json")
    audit = _load_json(audit_path)
    matrix = _load_json(matrix_path)
    audit_sha = sha256_file(audit_path)
    matrix_sha = sha256_file(matrix_path)
    if audit_manifest.get("audit_sha256") != audit_sha:
        raise P7CInputError("P7 audit SHA-256 mismatch")
    if audit_manifest.get("failure_matrix_sha256") != matrix_sha:
        raise P7CInputError("P7 failure matrix SHA-256 mismatch")
    if (
        audit.get("run_id") != marker["RUN_ID"]
        or matrix.get("run_id") != marker["RUN_ID"]
    ):
        raise P7CInputError("P7/P7B run identity mismatch")
    source = P7CInputIdentity(
        p7b_output_directory=str(root),
        run_id=marker["RUN_ID"],
        commit_sha=marker["COMMIT_SHA"],
        execution_manifest_sha256=sha256_file(execution_manifest_path),
        execution_checksum_sha256=execution_checksum_sha,
        audit_sha256=audit_sha,
        failure_matrix_sha256=matrix_sha,
    )
    return source, audit, matrix


def _classification(
    category: str,
) -> tuple[P7CRemediationClass, P7CPriority, P7CRerunScope]:
    if category in EVIDENCE_FAILURES:
        return (
            P7CRemediationClass.EVIDENCE_REPAIR,
            P7CPriority.P0,
            P7CRerunScope.FULL_CROSS_LANE,
        )
    if category in ENVIRONMENT_FAILURES:
        return (
            P7CRemediationClass.ENVIRONMENT_REPAIR,
            P7CPriority.P1,
            P7CRerunScope.LANE_CAMPAIGN,
        )
    if category in IMPLEMENTATION_FAILURES:
        return (
            P7CRemediationClass.IMPLEMENTATION_REPAIR,
            P7CPriority.P1,
            P7CRerunScope.LANE_CAMPAIGN,
        )
    if category in TRANSIENT_FAILURES:
        return (
            P7CRemediationClass.TRANSIENT_RETRY,
            P7CPriority.P2,
            P7CRerunScope.LANE_CAMPAIGN,
        )
    return (
        P7CRemediationClass.MANUAL_TRIAGE,
        P7CPriority.P2,
        P7CRerunScope.LANE_CAMPAIGN,
    )


def _action(remediation: P7CRemediationClass, lane: str, model: str) -> str:
    if remediation is P7CRemediationClass.EVIDENCE_REPAIR:
        return (
            "Discard the affected certification claim and create a new "
            "immutable P7B run."
        )
    if remediation is P7CRemediationClass.ENVIRONMENT_REPAIR:
        return (
            f"Repair the isolated {lane} environment, then run a new "
            f"{lane} campaign."
        )
    if remediation is P7CRemediationClass.IMPLEMENTATION_REPAIR:
        return (
            f"Reproduce and fix {model} in the {lane} provider before a "
            "new lane campaign."
        )
    if remediation is P7CRemediationClass.TRANSIENT_RETRY:
        return (
            f"Inspect resource and process logs, then retry the immutable "
            f"{lane} campaign."
        )
    return f"Manually classify {model} in {lane}; do not promote it to available."


def _commands(lane: str, model: str) -> list[str]:
    return [
        (
            "jq '.rows[] | select(.lane==\""
            + lane
            + "\" and .model_class==\""
            + model
            + "\")' \"${P7B_OUT}/audit/p7_failure_matrix.json\""
        ),
        (
            f"grep -R --line-number --fixed-strings '{model}' "
            f"\"${{P7B_OUT}}/{lane}\" | head -200"
        ),
        (
            "RUN_ID=\"gluonts-p7c-rerun-$(date -u +%Y%m%dT%H%M%SZ)\" "
            "bash environments/gluonts-p7b-target-machine.sh \"${NEW_OUT}\""
        ),
    ]


def _model_item(row: dict[str, Any]) -> P7CRemediationItem:
    lane = str(row.get("lane", ""))
    model = str(row.get("model_class", ""))
    status = str(row.get("certification_status", "FAILED"))
    if lane not in {"compat", "latest"} or not model:
        raise P7CInputError(f"invalid failure matrix row identity: {row}")
    if status == "VERIFIED":
        return P7CRemediationItem(
            item_id=f"{lane}:{model}",
            lane=lane,
            model_class=model,
            current_status=status,
            failed_stage="none",
            remediation_class=P7CRemediationClass.VERIFIED,
            priority=P7CPriority.P4,
            rerun_scope=P7CRerunScope.NONE,
            preserve_verified=True,
            action=(
                "Keep this model-lane lifecycle immutable and do not rerun "
                "it for diagnosis."
            ),
            reason=(
                "P7 contains valid VERIFIED fit, reload, artifact, and "
                "distinct-PID evidence."
            ),
            evidence_paths=["audit/p7_failure_matrix.json"],
            artifact_manifest_sha256=row.get("artifact_manifest_sha256"),
        )
    category = str(row.get("failure_category") or "UNKNOWN")
    remediation, priority, rerun_scope = _classification(category)
    raw_errors = row.get("errors") or ["unclassified model-lane failure"]
    errors = [str(error) for error in raw_errors]
    return P7CRemediationItem(
        item_id=f"{lane}:{model}",
        lane=lane,
        model_class=model,
        current_status=status,
        failed_stage=str(row.get("failed_stage") or "campaign"),
        failure_category=category,
        remediation_class=remediation,
        priority=priority,
        rerun_scope=rerun_scope,
        preserve_verified=True,
        action=_action(remediation, lane, model),
        reason=f"P7 classified {lane}/{model} as {status} with {category}.",
        errors=errors,
        evidence_paths=[
            "audit/p7_target_machine_audit.json",
            "audit/p7_failure_matrix.json",
            f"{lane}/p6_campaign_result.json",
        ],
        artifact_manifest_sha256=row.get("artifact_manifest_sha256"),
        commands=_commands(lane, model),
    )


def _evidence_item(audit: dict[str, Any]) -> P7CRemediationItem:
    state = str(audit.get("evidence_state", "INVALID"))
    status = str(audit.get("certification_status", "NOT_EVALUATED"))
    errors = [
        str(error)
        for error in audit.get("errors") or ["cross-lane evidence is not valid"]
    ]
    category = (
        "CHECKSUM_OR_MANIFEST_INVALID"
        if state == "INVALID"
        else "MISSING_OR_INCOMPLETE_EVIDENCE"
    )
    return P7CRemediationItem(
        item_id="cross_lane:evidence",
        lane="cross_lane",
        model_class="__EVIDENCE__",
        current_status=status,
        failed_stage="audit",
        failure_category=category,
        remediation_class=P7CRemediationClass.EVIDENCE_REPAIR,
        priority=P7CPriority.P0,
        rerun_scope=P7CRerunScope.FULL_CROSS_LANE,
        preserve_verified=True,
        action=(
            "Do not use the affected run for model claims; produce a new "
            "immutable P7B run."
        ),
        reason=f"P7 evidence state is {state}, so model-level results are not trustworthy.",
        errors=errors,
        evidence_paths=[
            "p7b_execution_manifest.json",
            "P7B_EXECUTION_SHA256SUMS",
            "audit/p7_target_machine_audit.json",
        ],
        commands=[
            "sha256sum -c \"${P7B_OUT}/P7B_EXECUTION_SHA256SUMS\"",
            (
                "RUN_ID=\"gluonts-p7c-evidence-rerun-"
                "$(date -u +%Y%m%dT%H%M%SZ)\" "
                "bash environments/gluonts-p7b-target-machine.sh \"${NEW_OUT}\""
            ),
        ],
    )


def build_remediation_plan(root: Path) -> P7CRemediationPlan:
    source, audit, matrix = verify_p7b_input(root)
    evidence_state = str(audit.get("evidence_state", "INVALID"))
    certification_status = str(
        audit.get("certification_status", "NOT_EVALUATED")
    )
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        raise P7CInputError("P7 failure matrix rows are missing")
    items: list[P7CRemediationItem] = []
    if evidence_state != "VALID":
        items.append(_evidence_item(audit))
    else:
        identities = [
            (str(row.get("lane")), str(row.get("model_class")))
            for row in rows
        ]
        expected = {
            (lane, model)
            for lane in ("compat", "latest")
            for model in EXPECTED_MODELS
        }
        if (
            len(rows) != 18
            or set(identities) != expected
            or len(set(identities)) != 18
        ):
            raise P7CInputError(
                "valid P7 evidence requires exactly 18 unique model-lane rows"
            )
        items.extend(_model_item(row) for row in rows)
    verified = sum(
        item.remediation_class is P7CRemediationClass.VERIFIED
        for item in items
        if item.lane != "cross_lane"
    )
    audit_verified = audit.get("verified_model_lifecycles")
    if evidence_state == "VALID" and audit_verified != verified:
        raise P7CInputError(
            "P7 verified lifecycle count does not match the failure matrix"
        )
    if certification_status == "VERIFIED" and verified != 18:
        raise P7CInputError(
            "P7 VERIFIED certification requires 18 verified lifecycle rows"
        )
    counts = Counter(item.remediation_class.value for item in items)
    if evidence_state != "VALID":
        next_action = (
            "Repair evidence production and create a new immutable P7B run "
            "before model triage."
        )
    elif verified == 18 and certification_status == "VERIFIED":
        next_action = (
            "All 18 lifecycles are verified; P8 chronological evaluation may begin."
        )
    elif counts[P7CRemediationClass.ENVIRONMENT_REPAIR.value]:
        next_action = (
            "Repair isolated runtime environments before changing model code."
        )
    elif counts[P7CRemediationClass.IMPLEMENTATION_REPAIR.value]:
        next_action = (
            "Fix P1 implementation failures, then create a new immutable P7B run."
        )
    elif counts[P7CRemediationClass.TRANSIENT_RETRY.value]:
        next_action = (
            "Inspect process and resource evidence, then retry in a new "
            "immutable run."
        )
    else:
        next_action = "Complete manual classification; P8 remains blocked."
    plan = P7CRemediationPlan(
        source=source,
        evidence_state=evidence_state,
        certification_status=certification_status,
        verified_model_lifecycles=verified,
        p8_eligible=(
            evidence_state == "VALID"
            and certification_status == "VERIFIED"
            and verified == 18
        ),
        counts=dict(sorted(counts.items())),
        items=items,
        recommended_next_action=next_action,
        errors=[str(error) for error in audit.get("errors") or []],
    )
    return plan


def _validate_output_location(input_root: Path, output_dir: Path) -> None:
    source = input_root.resolve()
    output = output_dir.resolve()
    if output == source or source in output.parents:
        raise ValueError(
            "P7C output must not be inside the immutable P7B input directory"
        )
    if output.exists() and any(output.iterdir()):
        raise ValueError("P7C output directory must be absent or empty")


def _write_tsv(path: Path, plan: P7CRemediationPlan) -> None:
    columns = (
        "priority",
        "remediation_class",
        "lane",
        "model_class",
        "current_status",
        "failed_stage",
        "failure_category",
        "rerun_scope",
        "preserve_verified",
        "action",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for item in plan.items:
            writer.writerow(
                {
                    "priority": item.priority.value,
                    "remediation_class": item.remediation_class.value,
                    "lane": item.lane,
                    "model_class": item.model_class,
                    "current_status": item.current_status,
                    "failed_stage": item.failed_stage,
                    "failure_category": item.failure_category or "",
                    "rerun_scope": item.rerun_scope.value,
                    "preserve_verified": str(item.preserve_verified).lower(),
                    "action": item.action,
                }
            )


def _write_markdown(path: Path, plan: P7CRemediationPlan) -> None:
    lines = [
        "# GluonTS P7C remediation report",
        "",
        f"- Run ID: `{plan.source.run_id}`",
        f"- Commit: `{plan.source.commit_sha}`",
        f"- Evidence: `{plan.evidence_state}`",
        f"- Certification: `{plan.certification_status}`",
        (
            "- Verified model-lane lifecycles: "
            f"**{plan.verified_model_lifecycles}/18**"
        ),
        f"- P8 eligible: **{str(plan.p8_eligible).upper()}**",
        "",
        "## Recommended next action",
        "",
        plan.recommended_next_action,
        "",
        "## Remediation queue",
        "",
        "| Priority | Class | Lane | Model | Status | Failure | Rerun |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in plan.items:
        lines.append(
            "| "
            + " | ".join(
                (
                    item.priority.value,
                    item.remediation_class.value,
                    item.lane,
                    item.model_class,
                    item.current_status,
                    item.failure_category or "-",
                    item.rerun_scope.value,
                )
            )
            + " |"
        )
    lines.extend(("", "## Input identity", ""))
    for key, value in plan.source.model_dump(mode="json").items():
        lines.append(f"- `{key}`: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_remediation_outputs(
    input_root: Path,
    output_dir: Path,
    plan: P7CRemediationPlan,
) -> dict[str, str]:
    _validate_output_location(input_root, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "p7c_remediation_plan.json"
    queue_path = output_dir / "p7c_remediation_queue.tsv"
    report_path = output_dir / "p7c_remediation_report.md"
    plan_sha = atomic_write_json(plan_path, plan.model_dump(mode="json"))
    _write_tsv(queue_path, plan)
    _write_markdown(report_path, plan)
    manifest = {
        "schema_version": 1,
        "phase": plan.phase,
        "run_id": plan.source.run_id,
        "source_commit_sha": plan.source.commit_sha,
        "source_execution_manifest_sha256": (
            plan.source.execution_manifest_sha256
        ),
        "source_execution_checksum_sha256": (
            plan.source.execution_checksum_sha256
        ),
        "source_audit_sha256": plan.source.audit_sha256,
        "source_failure_matrix_sha256": plan.source.failure_matrix_sha256,
        "plan_sha256": plan_sha,
        "queue_sha256": sha256_file(queue_path),
        "report_sha256": sha256_file(report_path),
        "p8_eligible": plan.p8_eligible,
    }
    manifest_path = output_dir / "p7c_artifact_manifest.json"
    manifest_sha = atomic_write_json(manifest_path, manifest)
    sums_path = output_dir / "P7C_SHA256SUMS"
    lines = [
        f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}"
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "P7C_SHA256SUMS"
    ]
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "plan_sha256": plan_sha,
        "queue_sha256": manifest["queue_sha256"],
        "report_sha256": manifest["report_sha256"],
        "manifest_sha256": manifest_sha,
        "checksums_sha256": sha256_file(sums_path),
    }
