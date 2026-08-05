"""Compose the promotion gate with chronological lineage enforcement."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import CampaignConfig, CampaignStage
from .lineage_integrity import evaluate_lineage_inputs, write_run_lineage
from .persistence import verify_sha256s, write_json
from .promotion_gate import evaluate_promotion_gate, run_stage_with_promotion_gate


def _verified_run_failures(path: Path, label: str) -> list[str]:
    failures: list[str] = []
    report_path = path / "VERIFICATION_REPORT.json"
    if not report_path.is_file():
        return [f"{label} VERIFICATION_REPORT.json missing"]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{label} verification report unreadable: {type(exc).__name__}: {exc}"]
    if not isinstance(report, dict) or report.get("status") != "PASS":
        failures.append(
            f"{label} verification report status is not PASS: "
            f"{report.get('status') if isinstance(report, dict) else None}"
        )
    for failure in verify_sha256s(path):
        failures.append(f"{label} SHA256: {failure}")
    return failures


def _input_verification_failures(
    *,
    target_stage: CampaignStage,
    source_run: Path | None,
    predecessor_run: Path | None,
) -> list[str]:
    failures: list[str] = []
    checked: set[Path] = set()
    for path, label in (
        (source_run, "source run"),
        (predecessor_run, "predecessor run"),
    ):
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in checked:
            continue
        checked.add(resolved)
        failures.extend(_verified_run_failures(resolved, label))

    if target_stage == CampaignStage.HPO and checked:
        failures.append("hpo must not receive source or predecessor runs")
    return failures


def run_stage_with_promotion_and_lineage(
    *,
    runner: Callable[..., dict[str, Any]],
    project_root: Path,
    config: CampaignConfig,
    run_root: Path,
    target_stage: CampaignStage,
    source_run: Path | None,
    predecessor_run: Path | None,
    coverage_run: Path | None,
    runtime_run: Path | None,
    resume: bool,
) -> dict[str, Any]:
    """Block invalid chains, run the existing gate, then freeze lineage."""

    lineage_input = evaluate_lineage_inputs(
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
    )
    verification_failures = _input_verification_failures(
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
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

    return write_run_lineage(
        run_root=run_root,
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
        coverage_run=coverage_run,
        runtime_run=runtime_run,
    )
