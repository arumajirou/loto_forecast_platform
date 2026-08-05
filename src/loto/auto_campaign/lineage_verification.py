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
from .verification_seal import (
    verify_verification_seal,
    write_verification_seal,
)

_SEMANTIC_SOURCE_STAGE = {
    CampaignStage.HPO: None,
    CampaignStage.VALIDATE_TRIALS: CampaignStage.HPO,
    CampaignStage.OOF: CampaignStage.VALIDATE_TRIALS,
    CampaignStage.HOLDOUT: CampaignStage.VALIDATE_TRIALS,
    CampaignStage.PROSPECTIVE: CampaignStage.VALIDATE_TRIALS,
}

_SEMANTIC_PREDECESSOR_STAGE = {
    CampaignStage.HPO: None,
    CampaignStage.VALIDATE_TRIALS: CampaignStage.HPO,
    CampaignStage.OOF: CampaignStage.VALIDATE_TRIALS,
    CampaignStage.HOLDOUT: CampaignStage.OOF,
    CampaignStage.PROSPECTIVE: CampaignStage.HOLDOUT,
}


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


def _evidence_stage(
    evidence: Any,
    expected: CampaignStage | None,
    failures: list[str],
    label: str,
) -> None:
    if expected is None:
        if evidence is not None:
            failures.append(f"{label} must be absent")
        return
    if not isinstance(evidence, Mapping):
        failures.append(f"{label} must be a non-empty object")
        return
    if evidence.get("stage") != expected.value:
        failures.append(
            f"{label} stage mismatch: expected={expected.value}, "
            f"actual={evidence.get('stage')}"
        )
    if evidence.get("verification_status") != "PASS":
        failures.append(f"{label} verification_status must be PASS")
    if not str(evidence.get("path") or "").strip():
        failures.append(f"{label} path missing")


def verify_lineage_semantics(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate stage ordering independently of recorded hashes."""

    lineage_path = run_root / "LINEAGE.json"
    if not lineage_path.is_file():
        return {"status": "NOT_APPLICABLE", "failures": []}
    failures: list[str] = []
    lineage = _read_json(lineage_path, failures, "lineage")
    raw_stage = str(lineage.get("target_stage") or "")
    try:
        target_stage = CampaignStage(raw_stage)
    except ValueError:
        failures.append(f"lineage target_stage is unknown: {raw_stage}")
        target_stage = None

    if target_stage not in GATED_STAGES:
        failures.append(f"lineage target stage is not gated: {raw_stage}")
    if raw_stage != str(manifest.get("stage") or ""):
        failures.append("lineage target stage differs from run manifest")

    source = lineage.get("source_evidence")
    predecessor = lineage.get("predecessor_evidence")
    if target_stage in GATED_STAGES:
        expected_source = _SEMANTIC_SOURCE_STAGE[target_stage]
        expected_predecessor = _SEMANTIC_PREDECESSOR_STAGE[target_stage]
        _evidence_stage(source, expected_source, failures, "source evidence")
        _evidence_stage(
            predecessor,
            expected_predecessor,
            failures,
            "predecessor evidence",
        )
        if target_stage in {CampaignStage.VALIDATE_TRIALS, CampaignStage.OOF}:
            if isinstance(source, Mapping) and isinstance(predecessor, Mapping):
                if source.get("path") != predecessor.get("path"):
                    failures.append(
                        f"{target_stage.value} source and predecessor paths must match"
                    )
        if target_stage in {CampaignStage.HOLDOUT, CampaignStage.PROSPECTIVE}:
            if isinstance(source, Mapping) and isinstance(predecessor, Mapping):
                if source.get("path") == predecessor.get("path"):
                    failures.append(
                        f"{target_stage.value} predecessor must differ from config source"
                    )

    run_evidence = lineage.get("run")
    if not isinstance(run_evidence, Mapping):
        failures.append("lineage run evidence must be an object")
    else:
        if not str(run_evidence.get("manifest_code_sha256") or "").strip():
            failures.append("lineage run code SHA-256 missing")
        if not str(run_evidence.get("manifest_data_sha256") or "").strip():
            failures.append("lineage run data SHA-256 missing")

    coverage = lineage.get("coverage_evidence")
    if not isinstance(coverage, Mapping):
        failures.append("coverage evidence must be an object")
    elif coverage.get("verification_status") != "PASS":
        failures.append("coverage evidence verification_status must be PASS")

    gate_failures: list[str] = []
    gate = _read_json(run_root / "PROMOTION_GATE.json", gate_failures, "promotion gate")
    failures.extend(gate_failures)
    runtime = lineage.get("runtime_evidence")
    if gate.get("requires_gpu_runtime") is True:
        if not isinstance(runtime, Mapping):
            failures.append("GPU lineage requires runtime evidence")
        elif runtime.get("verification_status") != "PASS":
            failures.append("GPU runtime evidence verification_status must be PASS")
    elif isinstance(runtime, Mapping) and runtime.get("verification_status") != "PASS":
        failures.append("optional runtime evidence verification_status must be PASS")

    return {
        "status": "PASS" if not failures else "FAIL",
        "target_stage": raw_stage or None,
        "failures": failures,
    }


def _existing_seal_result(run_root: Path) -> dict[str, Any]:
    if not (run_root / "VERIFICATION_SEAL.json").is_file():
        return {"status": "NOT_APPLICABLE", "failures": []}
    return verify_verification_seal(run_root)


def verify_run_with_lineage(run_root: Path) -> dict[str, Any]:
    """Run legacy, coverage, promotion-gate, lineage, and seal checks."""

    from .coverage_verification import verify_run_with_coverage

    existing_seal = _existing_seal_result(run_root)
    base_result = verify_run_with_coverage(run_root)
    manifest_failures: list[str] = []
    manifest = _read_json(run_root / "manifest.json", manifest_failures, "run manifest")
    promotion_result = verify_promotion_gate_artifacts(run_root, manifest)
    lineage_result = verify_lineage_artifacts(run_root, manifest)
    semantic_result = verify_lineage_semantics(run_root, manifest)

    if semantic_result.get("status") == "FAIL":
        lineage_failures = list(lineage_result.get("failures") or [])
        lineage_failures.extend(semantic_result.get("failures") or [])
        lineage_result = {
            **lineage_result,
            "status": "FAIL",
            "semantic_verification": semantic_result,
            "failures": lineage_failures,
        }
    else:
        lineage_result = {
            **lineage_result,
            "semantic_verification": semantic_result,
        }

    stage = str(manifest.get("stage") or "")
    gated_values = {item.value for item in GATED_STAGES}
    if stage in gated_values and lineage_result.get("status") == "NOT_APPLICABLE":
        lineage_result = {
            "applicable": True,
            "status": "FAIL",
            "target_stage": stage,
            "chain_sha256": None,
            "semantic_verification": semantic_result,
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
    if existing_seal.get("status") == "FAIL":
        failures.extend(
            f"verification-seal:{failure}"
            for failure in existing_seal.get("failures", [])
        )

    result: dict[str, Any] = {
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
        "preexisting_verification_seal": existing_seal,
        "failures": failures,
    }

    seal_payload = None
    if result["status"] == "PASS":
        try:
            seal_payload = write_verification_seal(run_root, result)
        except (OSError, ValueError) as exc:
            failures.append(f"verification-seal:create:{type(exc).__name__}: {exc}")
            result["status"] = "FAIL"
            result["failures"] = failures

    if seal_payload is not None:
        seal_result = verify_verification_seal(run_root)
        if seal_result.get("status") != "PASS":
            failures.extend(
                f"verification-seal:{failure}"
                for failure in seal_result.get("failures", [])
            )
            result["status"] = "FAIL"
            result["failures"] = failures
    else:
        seal_result = existing_seal
    result["verification_seal"] = seal_result
    if result["status"] == "PASS":
        # Normalize first and repeated PASS reports to the same final seal state.
        result["preexisting_verification_seal"] = seal_result

    write_json(run_root / "VERIFICATION_REPORT.json", result)
    write_sha256s(run_root)
    return result
