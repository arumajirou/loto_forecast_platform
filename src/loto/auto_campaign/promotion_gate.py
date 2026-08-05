"""Fail-closed promotion gate for downstream AutoModel campaign stages.

API-contract evidence and runtime evidence are deliberately separate. CPU-only
coverage evidence can authorize a CPU campaign, but it can never certify a GPU
campaign. GPU stages require a complete 36-model runtime campaign with formal
training-worker proof, CUDA inference before save and after reload, GPU PID and
VRAM evidence, finite outputs, and no CPU fallback.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import CampaignConfig, CampaignStage
from .coverage_verification import verify_coverage_state_artifacts
from .persistence import sha256_file, verify_sha256s, write_json, write_sha256s

GATED_STAGES = frozenset(
    {
        CampaignStage.HPO,
        CampaignStage.VALIDATE_TRIALS,
        CampaignStage.OOF,
        CampaignStage.HOLDOUT,
        CampaignStage.PROSPECTIVE,
    }
)


def _read_json_object(path: Path, failures: list[str], label: str) -> dict[str, Any]:
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


def _requires_gpu(config: CampaignConfig) -> bool:
    resources = config.resources
    return bool(
        resources.accelerator == "gpu"
        or resources.gpus_per_trial > 0
    )


def _cuda_device(snapshot: Mapping[str, Any]) -> bool:
    return bool(
        str(snapshot.get("parameter_device") or "").startswith("cuda")
        or str(snapshot.get("trainer_root_device") or "").startswith("cuda")
    )


def _vram_evidence(snapshot: Mapping[str, Any]) -> bool:
    metrics = (
        "cuda_memory_allocated",
        "cuda_memory_reserved",
        "cuda_peak_memory_allocated",
    )
    for key in metrics:
        try:
            if float(snapshot.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _coverage_decision(coverage_run: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    manifest_path = coverage_run / "manifest.json"
    manifest = _read_json_object(manifest_path, failures, "coverage manifest")
    verification_path = coverage_run / "VERIFICATION_REPORT.json"
    verification = _read_json_object(
        verification_path,
        failures,
        "coverage verification report",
    )

    for failure in verify_sha256s(coverage_run):
        failures.append(f"coverage root SHA256: {failure}")

    artifact_verification: dict[str, Any] = {}
    if manifest:
        artifact_verification = verify_coverage_state_artifacts(coverage_run, manifest)
        failures.extend(
            f"coverage artifact: {failure}"
            for failure in artifact_verification.get("failures", [])
        )
        if manifest.get("status") != "PASS":
            failures.append(f"coverage manifest status is not PASS: {manifest.get('status')}")
        if manifest.get("coverage_state_status") != "VERIFIED":
            failures.append(
                "coverage_state_status must be VERIFIED: "
                f"actual={manifest.get('coverage_state_status')}"
            )
        if manifest.get("verification_status") != "VERIFIED":
            failures.append(
                "coverage verification_status must be VERIFIED: "
                f"actual={manifest.get('verification_status')}"
            )

    if verification:
        if verification.get("status") != "PASS":
            failures.append(
                "coverage VERIFICATION_REPORT status must be PASS: "
                f"actual={verification.get('status')}"
            )
        nested = verification.get("coverage_state_verification")
        if not isinstance(nested, Mapping) or nested.get("status") != "PASS":
            failures.append("coverage_state_verification must be PASS")

    evidence = {
        "run": str(coverage_run.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "verification_report_path": str(verification_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        "verification_report_sha256": (
            sha256_file(verification_path) if verification_path.is_file() else None
        ),
        "manifest_status": manifest.get("status"),
        "coverage_state_status": manifest.get("coverage_state_status"),
        "verification_status": manifest.get("verification_status"),
        "artifact_verification_status": artifact_verification.get("status"),
        "status": "PASS" if not failures else "FAIL",
    }
    return evidence, failures


def _runtime_report_path(runtime_run: Path) -> Path:
    return runtime_run if runtime_run.is_file() else runtime_run / "campaign_report.json"


def _runtime_decision(
    runtime_run: Path,
    *,
    expected_model_count: int,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    report_path = _runtime_report_path(runtime_run)
    report = _read_json_object(report_path, failures, "runtime campaign report")
    rows = report.get("reports") if report else None
    if not isinstance(rows, list) or not rows:
        failures.append("runtime campaign reports must be a non-empty list")
        rows = []

    if report:
        if report.get("status") != "SUCCEEDED":
            failures.append(f"runtime campaign status is not SUCCEEDED: {report.get('status')}")
        if report.get("certification_status") != "RUNTIME_CERTIFIED":
            failures.append(
                "runtime certification_status must be RUNTIME_CERTIFIED: "
                f"actual={report.get('certification_status')}"
            )
        for key, expected in (
            ("started_model_count", expected_model_count),
            ("succeeded_model_count", expected_model_count),
            ("runtime_certified_model_count", expected_model_count),
            ("failed_model_count", 0),
        ):
            if report.get(key) != expected:
                failures.append(
                    f"runtime {key} mismatch: expected={expected}, actual={report.get(key)}"
                )

    model_ids: list[str] = []
    failed_models: list[str] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            failures.append(f"runtime report row {index} is not an object")
            continue
        model_id = str(raw.get("model_id") or raw.get("class_name") or "").strip()
        model_ids.append(model_id)
        prefix = f"runtime model {model_id or index}"
        certification = raw.get("runtime_certification")
        checks = {
            "model_status": raw.get("status") == "SUCCEEDED",
            "model_certification_status": (
                raw.get("certification_status") == "RUNTIME_CERTIFIED"
            ),
            "certification_object": isinstance(certification, Mapping),
        }
        if isinstance(certification, Mapping):
            pre_runtime = certification.get("runtime_pre_save_inference")
            reload_runtime = certification.get("runtime_reload_inference")
            pre_gpu = certification.get("gpu_pre_save_inference")
            reload_gpu = certification.get("gpu_reload_inference")
            checks.update(
                {
                    "certification_status": certification.get("status") == "PASS",
                    "require_gpu": certification.get("require_gpu") is True,
                    "formal_training_cuda": (
                        certification.get("formal_cuda_training_evidence") is True
                    ),
                    "pre_save_cuda": (
                        certification.get("cuda_pre_save_inference_evidence") is True
                    ),
                    "reload_cuda": (
                        certification.get("cuda_reload_inference_evidence") is True
                    ),
                    "combined_cuda": certification.get("cuda_execution_evidence") is True,
                    "no_cpu_fallback": certification.get("cpu_fallback") is False,
                    "loaded": certification.get("loaded") is True,
                    "predicted": certification.get("predicted") is True,
                    "shape_match": certification.get("shape_match") is True,
                    "key_match": certification.get("key_match") is True,
                    "finite": certification.get("finite") is True,
                    "prediction_match": certification.get("prediction_match") is True,
                    "state_before_finite": (
                        certification.get("state_before_finite") is True
                    ),
                    "state_after_finite": certification.get("state_after_finite") is True,
                    "training_evidence_present": bool(certification.get("training_evidence")),
                    "pre_save_device_cuda": (
                        isinstance(pre_runtime, Mapping) and _cuda_device(pre_runtime)
                    ),
                    "reload_device_cuda": (
                        isinstance(reload_runtime, Mapping) and _cuda_device(reload_runtime)
                    ),
                    "pre_save_vram": (
                        isinstance(pre_runtime, Mapping) and _vram_evidence(pre_runtime)
                    ),
                    "reload_vram": (
                        isinstance(reload_runtime, Mapping) and _vram_evidence(reload_runtime)
                    ),
                    "pre_save_gpu_pid": (
                        isinstance(pre_gpu, Mapping)
                        and pre_gpu.get("gpu_pid_verified") is True
                    ),
                    "reload_gpu_pid": (
                        isinstance(reload_gpu, Mapping)
                        and reload_gpu.get("gpu_pid_verified") is True
                    ),
                }
            )
        missing = sorted(name for name, passed in checks.items() if not passed)
        if missing:
            failed_models.append(model_id or str(index))
            failures.append(f"{prefix} failed checks: {missing}")

    if len(rows) != expected_model_count:
        failures.append(
            "runtime report model row count mismatch: "
            f"expected={expected_model_count}, actual={len(rows)}"
        )
    if len(set(model_ids)) != len(model_ids) or any(not model_id for model_id in model_ids):
        failures.append("runtime model IDs are empty or duplicated")

    evidence = {
        "run": str(runtime_run.resolve()),
        "campaign_report_path": str(report_path.resolve()),
        "campaign_report_sha256": sha256_file(report_path) if report_path.is_file() else None,
        "campaign_status": report.get("status"),
        "certification_status": report.get("certification_status"),
        "expected_model_count": expected_model_count,
        "observed_model_count": len(rows),
        "failed_models": sorted(failed_models),
        "status": "PASS" if not failures else "FAIL",
    }
    return evidence, failures


def evaluate_promotion_gate(
    *,
    config: CampaignConfig,
    target_stage: CampaignStage,
    coverage_run: Path | None,
    runtime_run: Path | None = None,
    expected_model_count: int = 36,
) -> dict[str, Any]:
    """Evaluate whether a downstream stage may start."""

    if target_stage not in GATED_STAGES:
        return {
            "schema_version": "all-auto-promotion-gate-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "NOT_APPLICABLE",
            "target_stage": target_stage.value,
            "requires_gpu_runtime": False,
            "failures": [],
        }

    failures: list[str] = []
    coverage_evidence: dict[str, Any] = {}
    runtime_evidence: dict[str, Any] | None = None
    if coverage_run is None:
        failures.append(f"{target_stage.value} requires --coverage-run")
    else:
        coverage_evidence, coverage_failures = _coverage_decision(coverage_run.resolve())
        failures.extend(coverage_failures)

    requires_gpu = _requires_gpu(config)
    if requires_gpu:
        if runtime_run is None:
            failures.append(
                f"{target_stage.value} requests GPU resources and requires --runtime-run"
            )
        else:
            runtime_evidence, runtime_failures = _runtime_decision(
                runtime_run.resolve(),
                expected_model_count=expected_model_count,
            )
            failures.extend(runtime_failures)
    elif runtime_run is not None:
        runtime_evidence, runtime_failures = _runtime_decision(
            runtime_run.resolve(),
            expected_model_count=expected_model_count,
        )
        failures.extend(runtime_failures)

    return {
        "schema_version": "all-auto-promotion-gate-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if not failures else "BLOCKED",
        "target_stage": target_stage.value,
        "requires_gpu_runtime": requires_gpu,
        "expected_model_count": expected_model_count,
        "coverage_evidence": coverage_evidence,
        "runtime_evidence": runtime_evidence,
        "failures": failures,
    }


def run_stage_with_promotion_gate(
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
) -> dict[str, Any]:
    """Apply the gate, then execute the existing stage runner without replacing it."""

    decision = evaluate_promotion_gate(
        config=config,
        target_stage=target_stage,
        coverage_run=coverage_run,
        runtime_run=runtime_run,
    )
    if decision["status"] != "PASS":
        sidecar = run_root.with_name(f"{run_root.name}.PROMOTION_GATE_BLOCKED.json")
        write_json(sidecar, decision)
        return {
            "status": "BLOCKED",
            "stage": target_stage.value,
            "promotion_gate_status": decision["status"],
            "promotion_gate_path": str(sidecar),
            "promotion_gate": decision,
        }

    result = runner(
        project_root,
        config,
        run_root,
        target_stage,
        source_run=source_run,
        resume=resume,
    )
    gate_path = run_root / "PROMOTION_GATE.json"
    write_json(gate_path, decision)
    manifest_path = run_root / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = dict(result)
    manifest.update(
        {
            "promotion_gate_status": "PASS",
            "promotion_gate_path": "PROMOTION_GATE.json",
            "promotion_gate": decision,
        }
    )
    write_json(manifest_path, manifest)
    write_sha256s(run_root)
    return manifest
