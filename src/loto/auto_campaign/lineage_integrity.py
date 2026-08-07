"""Immutable lineage evidence for gated AutoModel campaign stages.

The lineage contract records the exact evidence used to authorize a run and
re-verifies it later.  Configuration selection and chronological progression
are deliberately separate: ``source_run`` remains the configuration source,
while ``predecessor_run`` records the immediately preceding evaluation stage.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import CampaignStage
from .persistence import sha256_file, verify_sha256s, write_json, write_sha256s

LINEAGE_SCHEMA_VERSION = "all-auto-lineage-v1"

_SOURCE_STAGE = {
    CampaignStage.HPO: None,
    CampaignStage.VALIDATE_TRIALS: CampaignStage.HPO,
    CampaignStage.OOF: CampaignStage.VALIDATE_TRIALS,
    CampaignStage.HOLDOUT: CampaignStage.VALIDATE_TRIALS,
    CampaignStage.PROSPECTIVE: CampaignStage.VALIDATE_TRIALS,
}

_PREDECESSOR_STAGE = {
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


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_evidence(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def _run_evidence(
    run: Path,
    *,
    label: str,
    expected_stage: CampaignStage | None = None,
    require_lineage: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    root = run.resolve()
    if not root.is_dir():
        failures.append(f"{label} is not a directory: {root}")
        return {"path": str(root), "status": "FAIL"}, failures

    manifest_path = root / "manifest.json"
    sums_path = root / "SHA256SUMS"
    manifest = _read_json(manifest_path, failures, f"{label} manifest")
    for failure in verify_sha256s(root):
        failures.append(f"{label} SHA256: {failure}")

    observed_stage = str(manifest.get("stage") or "")
    if expected_stage is not None and observed_stage != expected_stage.value:
        failures.append(
            f"{label} stage mismatch: expected={expected_stage.value}, actual={observed_stage}"
        )
    if manifest and manifest.get("status") != "PASS":
        failures.append(f"{label} manifest status is not PASS: {manifest.get('status')}")

    lineage_path = root / "LINEAGE.json"
    if require_lineage:
        if manifest.get("lineage_status") != "PASS":
            failures.append(
                f"{label} lineage_status is not PASS: {manifest.get('lineage_status')}"
            )
        if not lineage_path.is_file():
            failures.append(f"{label} LINEAGE.json missing")
        elif manifest.get("lineage_sha256") != sha256_file(lineage_path):
            failures.append(f"{label} lineage_sha256 mismatch")

    evidence = {
        "path": str(root),
        "manifest": _file_evidence(manifest_path),
        "sha256s": _file_evidence(sums_path),
        "stage": observed_stage or None,
        "status": manifest.get("status"),
        "run_id": manifest.get("run_id"),
        "code_sha256": manifest.get("code_sha256"),
        "data_sha256": manifest.get("data_sha256"),
        "lineage_status": manifest.get("lineage_status"),
        "lineage": _file_evidence(lineage_path) if lineage_path.is_file() else None,
        "verification_status": "PASS" if not failures else "FAIL",
    }
    return evidence, failures


def _runtime_evidence(runtime_run: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    report_path = runtime_run if runtime_run.is_file() else runtime_run / "campaign_report.json"
    report = _read_json(report_path, failures, "runtime campaign report")
    if report and report.get("status") != "SUCCEEDED":
        failures.append(f"runtime campaign status is not SUCCEEDED: {report.get('status')}")
    if report and report.get("certification_status") != "RUNTIME_CERTIFIED":
        failures.append(
            "runtime campaign certification_status is not RUNTIME_CERTIFIED: "
            f"{report.get('certification_status')}"
        )
    return {
        "path": str(runtime_run.resolve()),
        "campaign_report": _file_evidence(report_path),
        "status": report.get("status"),
        "certification_status": report.get("certification_status"),
        "verification_status": "PASS" if not failures else "FAIL",
    }, failures


def evaluate_lineage_inputs(
    *,
    target_stage: CampaignStage,
    source_run: Path | None,
    predecessor_run: Path | None,
) -> dict[str, Any]:
    """Validate chronological inputs before a gated stage starts."""

    failures: list[str] = []
    source_evidence: dict[str, Any] | None = None
    predecessor_evidence: dict[str, Any] | None = None
    expected_source = _SOURCE_STAGE.get(target_stage)
    expected_predecessor = _PREDECESSOR_STAGE.get(target_stage)

    if expected_source is None:
        if source_run is not None:
            failures.append(f"{target_stage.value} does not accept a source run")
    elif source_run is None:
        failures.append(
            f"{target_stage.value} requires source run stage={expected_source.value}"
        )
    else:
        source_evidence, source_failures = _run_evidence(
            source_run,
            label="source run",
            expected_stage=expected_source,
            require_lineage=True,
        )
        failures.extend(source_failures)

    if expected_predecessor is None:
        if predecessor_run is not None:
            failures.append(f"{target_stage.value} does not accept a predecessor run")
    elif target_stage in {CampaignStage.VALIDATE_TRIALS, CampaignStage.OOF}:
        if predecessor_run is not None and source_run is not None:
            if predecessor_run.resolve() != source_run.resolve():
                failures.append(
                    f"{target_stage.value} predecessor must equal its source run"
                )
        predecessor_evidence = source_evidence
    elif predecessor_run is None:
        failures.append(
            f"{target_stage.value} requires predecessor stage={expected_predecessor.value}"
        )
    else:
        predecessor_evidence, predecessor_failures = _run_evidence(
            predecessor_run,
            label="predecessor run",
            expected_stage=expected_predecessor,
            require_lineage=True,
        )
        failures.extend(predecessor_failures)

    return {
        "schema_version": "all-auto-lineage-input-check-v1",
        "status": "PASS" if not failures else "BLOCKED",
        "target_stage": target_stage.value,
        "expected_source_stage": None if expected_source is None else expected_source.value,
        "expected_predecessor_stage": (
            None if expected_predecessor is None else expected_predecessor.value
        ),
        "source_evidence": source_evidence,
        "predecessor_evidence": predecessor_evidence,
        "failures": failures,
    }


def _lineage_core(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"created_at", "chain_sha256"}
    }


def write_run_lineage(
    *,
    run_root: Path,
    target_stage: CampaignStage,
    source_run: Path | None,
    predecessor_run: Path | None,
    coverage_run: Path,
    runtime_run: Path | None,
) -> dict[str, Any]:
    """Persist the complete immutable evidence chain after stage execution."""

    input_check = evaluate_lineage_inputs(
        target_stage=target_stage,
        source_run=source_run,
        predecessor_run=predecessor_run,
    )
    if input_check["status"] != "PASS":
        raise ValueError(f"lineage inputs are not valid: {input_check['failures']}")

    failures: list[str] = []
    manifest_path = run_root / "manifest.json"
    manifest = _read_json(manifest_path, failures, "run manifest")
    config_path = run_root / "campaign_config.json"
    contract_path = run_root / "data_contract.json"
    gate_path = run_root / "PROMOTION_GATE.json"
    for path, label in (
        (config_path, "campaign config"),
        (contract_path, "data contract"),
        (gate_path, "promotion gate"),
    ):
        if not path.is_file():
            failures.append(f"{label} missing: {path}")

    coverage_evidence, coverage_failures = _run_evidence(
        coverage_run,
        label="coverage run",
    )
    failures.extend(coverage_failures)
    runtime_evidence: dict[str, Any] | None = None
    if runtime_run is not None:
        runtime_evidence, runtime_failures = _runtime_evidence(runtime_run)
        failures.extend(runtime_failures)

    payload: dict[str, Any] = {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "target_stage": target_stage.value,
        "run": {
            "path": str(run_root.resolve()),
            "campaign_config": _file_evidence(config_path),
            "data_contract": _file_evidence(contract_path),
            "promotion_gate": _file_evidence(gate_path),
            "manifest_code_sha256": manifest.get("code_sha256"),
            "manifest_data_sha256": manifest.get("data_sha256"),
        },
        "source_evidence": input_check.get("source_evidence"),
        "predecessor_evidence": input_check.get("predecessor_evidence"),
        "coverage_evidence": coverage_evidence,
        "runtime_evidence": runtime_evidence,
        "failures": failures,
    }
    payload["chain_sha256"] = _canonical_sha256(_lineage_core(payload))
    lineage_path = run_root / "LINEAGE.json"
    write_json(lineage_path, payload)

    manifest.update(
        {
            "lineage_schema_version": LINEAGE_SCHEMA_VERSION,
            "lineage_status": payload["status"],
            "lineage_path": "LINEAGE.json",
            "lineage_sha256": sha256_file(lineage_path),
            "lineage_chain_sha256": payload["chain_sha256"],
        }
    )
    if payload["status"] != "PASS":
        manifest["status"] = "PARTIAL"
    write_json(manifest_path, manifest)
    write_sha256s(run_root)
    return manifest


def _verify_recorded_file(
    evidence: Any,
    failures: list[str],
    label: str,
) -> Path | None:
    if not isinstance(evidence, Mapping):
        failures.append(f"{label} evidence must be an object")
        return None
    raw_path = str(evidence.get("path") or "").strip()
    expected = str(evidence.get("sha256") or "").strip()
    if not raw_path or not expected:
        failures.append(f"{label} evidence is incomplete")
        return None
    path = Path(raw_path)
    if not path.is_file():
        failures.append(f"{label} file missing: {path}")
        return None
    actual = sha256_file(path)
    if actual != expected:
        failures.append(f"{label} SHA256 mismatch: expected={expected}, actual={actual}")
    return path


def _verify_external_run(
    evidence: Any,
    failures: list[str],
    label: str,
) -> None:
    if not isinstance(evidence, Mapping):
        failures.append(f"{label} evidence must be an object")
        return
    root_value = str(evidence.get("path") or "").strip()
    if not root_value:
        failures.append(f"{label} path missing")
        return
    root = Path(root_value)
    if not root.is_dir():
        failures.append(f"{label} directory missing: {root}")
        return
    _verify_recorded_file(evidence.get("manifest"), failures, f"{label} manifest")
    _verify_recorded_file(evidence.get("sha256s"), failures, f"{label} SHA256SUMS")
    for failure in verify_sha256s(root):
        failures.append(f"{label} current SHA256: {failure}")
    manifest_failures: list[str] = []
    manifest = _read_json(root / "manifest.json", manifest_failures, f"{label} manifest")
    failures.extend(manifest_failures)
    for field in ("stage", "status", "code_sha256", "data_sha256", "lineage_status"):
        if evidence.get(field) != manifest.get(field):
            failures.append(
                f"{label} {field} changed: recorded={evidence.get(field)}, "
                f"current={manifest.get(field)}"
            )
    lineage = evidence.get("lineage")
    if lineage is not None:
        _verify_recorded_file(lineage, failures, f"{label} LINEAGE")


def verify_lineage_artifacts(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the lineage chain and reject any mutated dependency."""

    lineage_path = run_root / "LINEAGE.json"
    applicable = bool(manifest.get("lineage_status") is not None or lineage_path.exists())
    if not applicable:
        return {"applicable": False, "status": "NOT_APPLICABLE", "failures": []}

    failures: list[str] = []
    lineage = _read_json(lineage_path, failures, "lineage")
    required = {
        "lineage_schema_version",
        "lineage_status",
        "lineage_path",
        "lineage_sha256",
        "lineage_chain_sha256",
    }
    for field in sorted(required - set(manifest)):
        failures.append(f"run manifest missing lineage field: {field}")

    if str(manifest.get("lineage_path")) != "LINEAGE.json":
        failures.append("lineage_path must be LINEAGE.json")
    if manifest.get("lineage_schema_version") != LINEAGE_SCHEMA_VERSION:
        failures.append("run manifest lineage schema mismatch")
    if lineage.get("schema_version") != LINEAGE_SCHEMA_VERSION:
        failures.append("LINEAGE.json schema mismatch")
    if manifest.get("lineage_status") != "PASS" or lineage.get("status") != "PASS":
        failures.append("lineage status must be PASS")
    if lineage_path.is_file() and manifest.get("lineage_sha256") != sha256_file(lineage_path):
        failures.append("LINEAGE.json hash differs from run manifest")

    recomputed_chain = _canonical_sha256(_lineage_core(lineage)) if lineage else None
    if lineage.get("chain_sha256") != recomputed_chain:
        failures.append("LINEAGE.json chain_sha256 is invalid")
    if manifest.get("lineage_chain_sha256") != recomputed_chain:
        failures.append("run manifest lineage_chain_sha256 mismatch")
    if lineage.get("target_stage") != manifest.get("stage"):
        failures.append(
            "lineage target stage differs from run manifest: "
            f"lineage={lineage.get('target_stage')}, manifest={manifest.get('stage')}"
        )

    run_evidence = lineage.get("run")
    if not isinstance(run_evidence, Mapping):
        failures.append("lineage run evidence must be an object")
        run_evidence = {}
    _verify_recorded_file(
        run_evidence.get("campaign_config"),
        failures,
        "campaign config",
    )
    _verify_recorded_file(
        run_evidence.get("data_contract"),
        failures,
        "data contract",
    )
    _verify_recorded_file(
        run_evidence.get("promotion_gate"),
        failures,
        "promotion gate",
    )
    if run_evidence.get("manifest_code_sha256") != manifest.get("code_sha256"):
        failures.append("run code_sha256 differs from lineage")
    if run_evidence.get("manifest_data_sha256") != manifest.get("data_sha256"):
        failures.append("run data_sha256 differs from lineage")

    for key, label in (
        ("source_evidence", "source run"),
        ("predecessor_evidence", "predecessor run"),
        ("coverage_evidence", "coverage run"),
    ):
        evidence = lineage.get(key)
        if evidence is not None:
            _verify_external_run(evidence, failures, label)

    runtime_evidence = lineage.get("runtime_evidence")
    if runtime_evidence is not None:
        if not isinstance(runtime_evidence, Mapping):
            failures.append("runtime evidence must be an object")
        else:
            _verify_recorded_file(
                runtime_evidence.get("campaign_report"),
                failures,
                "runtime campaign report",
            )

    return {
        "applicable": True,
        "status": "PASS" if not failures else "FAIL",
        "target_stage": lineage.get("target_stage"),
        "chain_sha256": recomputed_chain,
        "failures": failures,
    }
