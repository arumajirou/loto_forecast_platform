"""Standard verification wrapper for promotion-gated lineage runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import CampaignStage
from .lineage_integrity import verify_lineage_artifacts
from .persistence import write_json, write_sha256s
from .promotion_gate import GATED_STAGES


def _read_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict) or not payload:
        failures.append(f"{label} must be a non-empty JSON object: {path}")
        return {}
    return payload


def verify_promotion_gate_artifacts(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the gate artifact and its exact embedded manifest copy."""

    gate_path = run_root / "PROMOTION_GATE.json"
    stage = str(manifest.get("stage") or "")
    gated_values = {item.value for item in GATED_STAGES}
    applicable = bool(
        stage in gated_values
        or gate_path.exists()
        or manifest.get("promotion_gate_status") is not None
    )
    if not applicable:
        return {"applicable": False, "status": "NOT_APPLICABLE", "failures": []}

    failures: list[str] = []
    gate = _read_json(gate_path, failures, "promotion gate")
    if stage not in gated_values:
        failures.append(f"promotion gate attached to ungated stage: {stage}")
    if manifest.get("promotion_gate_status") != "PASS":
        failures.append(
            "manifest promotion_gate_status must be PASS: "
            f"actual={manifest.get('promotion_gate_status')}"
        )
    if manifest.get("promotion_gate_path") != "PROMOTION_GATE.json":
        failures.append("manifest promotion_gate_path must be PROMOTION_GATE.json")
    embedded = manifest.get("promotion_gate")
    if not isinstance(embedded, Mapping) or not embedded:
        failures.append("manifest promotion_gate must be a non-empty object")
    elif gate and dict(embedded) != gate:
        failures.append("manifest promotion_gate differs from PROMOTION_GATE.json")

    if gate:
        if gate.get("schema_version") != "all-auto-promotion-gate-v1":
            failures.append("promotion gate schema_version mismatch")
        if gate.get("status") != "PASS":
            failures.append(f"promotion gate status is not PASS: {gate.get('status')}")
        if gate.get("target_stage") != stage:
            failures.append(
                "promotion gate target_stage mismatch: "
                f"gate={gate.get('target_stage')}, manifest={stage}"
            )
        if gate.get("failures") not in ([], None):
            failures.append("passing promotion gate contains failures")
        coverage = gate.get("coverage_evidence")
        if not isinstance(coverage, Mapping) or coverage.get("status") != "PASS":
            failures.append("promotion gate coverage evidence is not PASS")
        if gate.get("requires_gpu_runtime") is True:
            runtime = gate.get("runtime_evidence")
            if not isinstance(runtime, Mapping) or runtime.get("status") != "PASS":
                failures.append("GPU promotion gate runtime evidence is not PASS")

    return {
        "applicable": True,
        "status": "PASS" if not failures else "FAIL",
        "target_stage": stage or None,
        "requires_gpu_runtime": gate.get("requires_gpu_runtime"),
        "failures": failures,
    }


def verify_run_with_lineage(run_root: Path) -> dict[str, Any]:
    """Run legacy, coverage, promotion-gate, and lineage checks in order."""

    from .coverage_verification import verify_run_with_coverage

    base_result = verify_run_with_coverage(run_root)
    manifest_failures: list[str] = []
    manifest = _read_json(run_root / "manifest.json", manifest_failures, "run manifest")
    promotion_result = verify_promotion_gate_artifacts(run_root, manifest)
    lineage_result = verify_lineage_artifacts(run_root, manifest)

    stage = str(manifest.get("stage") or "")
    gated_values = {item.value for item in GATED_STAGES}
    if stage in gated_values and lineage_result.get("status") == "NOT_APPLICABLE":
        lineage_result = {
            "applicable": True,
            "status": "FAIL",
            "target_stage": stage,
            "chain_sha256": None,
            "failures": ["gated run is missing LINEAGE.json and lineage manifest fields"],
        }

    failures = list(base_result.get("failures") or [])
    failures.extend(f"manifest:{failure}" for failure in manifest_failures)
    failures.extend(
        f"promotion-gate:{failure}"
        for failure in promotion_result.get("failures", [])
    )
    failures.extend(
        f"lineage:{failure}"
        for failure in lineage_result.get("failures", [])
    )

    result = {
        **base_result,
        "status": (
            "PASS"
            if not failures
            and manifest.get("status") == "PASS"
            and promotion_result.get("status") in {"PASS", "NOT_APPLICABLE"}
            and lineage_result.get("status") in {"PASS", "NOT_APPLICABLE"}
            else "FAIL"
        ),
        "promotion_gate_verification": promotion_result,
        "lineage_verification": lineage_result,
        "failures": failures,
    }
    write_json(run_root / "VERIFICATION_REPORT.json", result)
    write_sha256s(run_root)
    return result
