"""Compose promotion, chronological lineage, and prospective locking."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import CampaignConfig, CampaignStage
from .lineage_integrity import evaluate_lineage_inputs, write_run_lineage
from .persistence import verify_sha256s, write_json, write_sha256s
from .prediction_lock import freeze_prospective_predictions
from .promotion_gate import evaluate_promotion_gate, run_stage_with_promotion_gate
from .verification_seal import verify_verification_seal


def _verified_run_failures(path: Path, label: str) -> list[str]:
    failures: list[str] = []
    report_path = path / "VERIFICATION_REPORT.json"
    if not report_path.is_file():
        failures.append(f"{label} VERIFICATION_REPORT.json missing")
    else:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{label} verification report unreadable: {type(exc).__name__}: {exc}")
        else:
            if not isinstance(report, dict) or report.get("status") != "PASS":
                failures.append(
                    f"{label} verification report status is not PASS: "
                    f"{report.get('status') if isinstance(report, dict) else None}"
                )

    seal = verify_verification_seal(path)
    failures.extend(f"{label} verification seal: {failure}" for failure in seal.get("failures", []))
    for failure in verify_sha256s(path):
        failures.append(f"{label} SHA256: {failure}")
    return failures


def _input_verification_failures(
    *,
    target_stage: CampaignStage,
    source_run: Path | None,
    predecessor_run: Path | None,
    coverage_run: Path | None,
) -> list[str]:
    failures: list[str] = []
    checked: set[Path] = set()
    for path, label in (
        (source_run, "source run"),
        (predecessor_run, "predecessor run"),
        (coverage_run, "coverage run"),
    ):
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in checked:
            continue
        checked.add(resolved)
        failures.extend(_verified_run_failures(resolved, label))

    if target_stage == CampaignStage.HPO and any(
        path is not None for path in (source_run, predecessor_run)
    ):
        failures.append("hpo must not receive source or predecessor runs")
    return failures


def _record_prediction_lock_failure(
    run_root: Path,
    exc: BaseException,
) -> dict[str, Any]:
    failure = {
        "schema_version": "all-auto-prediction-lock-failure-v1",
        "status": "FAILED",
        "failed_at": datetime.now(UTC).isoformat(),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "actual_known_at_lock": "UNKNOWN",
    }
    write_json(run_root / "PREDICTION_LOCK_FAILURE.json", failure)
    manifest_path = run_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": "PARTIAL",
            "prediction_lock_status": "FAILED",
            "prediction_lock_path": "PREDICTION_LOCK_FAILURE.json",
            "actual_known_at_lock": "UNKNOWN",
        }
    )
    write_json(manifest_path, manifest)
    write_sha256s(run_root)
    return {
        "status": "PARTIAL",
        "stage": CampaignStage.PROSPECTIVE.value,
        "lineage_status": manifest.get("lineage_status"),
        "prediction_lock_status": "FAILED",
        "prediction_lock_path": "PREDICTION_LOCK_FAILURE.json",
        "prediction_lock_failure": failure,
        "failures": [f"prediction-lock:{type(exc).__name__}: {exc}"],
    }


def run_stage_with_promotion_and_lineage(
    *,
    runner: Callable[..., dict[str, Any]],
    project_root: Path,
    config: CampaignConfig,
    run_root: Path,
    target_stage: CampaignStage,
    source_run: Path | None,
    coverage_run: Path | None,
    runtime_run: Path | None,
    resume: bool,
    predecessor_run: Path | None = None,
) -> dict[str, Any]:
    """Block invalid inputs, run the stage, freeze lineage, then lock predictions."""

    lineage_input = evaluate_lineage_inputs(
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
    )
    verification_failures = _input_verification_failures(
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
        coverage_run=coverage_run,
    )
    gate_decision = evaluate_promotion_gate(
        config=config,
        target_stage=target_stage,
        coverage_run=coverage_run,
        runtime_run=runtime_run,
    )
    failures = [
        *lineage_input.get("failures", []),
        *verification_failures,
        *gate_decision.get("failures", []),
    ]
    if failures:
        decision = {
            "schema_version": "all-auto-promotion-lineage-block-v1",
            "status": "BLOCKED",
            "stage": target_stage.value,
            "promotion_gate": gate_decision,
            "lineage_input": lineage_input,
            "failures": failures,
        }
        sidecar = run_root.with_name(f"{run_root.name}.PROMOTION_GATE_BLOCKED.json")
        write_json(sidecar, decision)
        return {
            "status": "BLOCKED",
            "stage": target_stage.value,
            "promotion_gate_status": gate_decision.get("status"),
            "lineage_input_status": lineage_input.get("status"),
            "promotion_gate_path": str(sidecar),
            "promotion_gate": gate_decision,
            "lineage_input": lineage_input,
            "failures": failures,
        }

    result = run_stage_with_promotion_gate(
        runner=runner,
        project_root=project_root,
        config=config,
        run_root=run_root,
        target_stage=target_stage,
        source_run=source_run,
        coverage_run=coverage_run,
        runtime_run=runtime_run,
        resume=resume,
    )
    if result.get("status") != "PASS":
        return {
            **result,
            "lineage_status": "NOT_WRITTEN_RUN_NOT_PASS",
            "lineage_input": lineage_input,
        }
    if coverage_run is None:
        raise AssertionError("passing promotion gate must have a coverage run")

    lineage_result = write_run_lineage(
        run_root=run_root,
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
        coverage_run=coverage_run,
        runtime_run=runtime_run,
    )
    if target_stage != CampaignStage.PROSPECTIVE:
        return lineage_result

    try:
        lock_result = freeze_prospective_predictions(run_root)
    except (OSError, ValueError) as exc:
        return _record_prediction_lock_failure(run_root, exc)
    return {
        **lineage_result,
        **lock_result,
        "lineage_status": lineage_result.get("lineage_status", "PASS"),
    }
