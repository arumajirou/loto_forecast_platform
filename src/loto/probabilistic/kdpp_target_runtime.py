from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.probabilistic.kdpp_certification_gate import (
    KDPPFormalVerificationReport,
    KDPPProcessRecord,
    sha256_file,
    validate_history_bundle,
    verify_inventory,
    verify_runtime_directory,
)
from loto.probabilistic.kdpp_target_contracts import TargetExecutionPlan, _load_object


def _validate_cpu_formal(
    runtime_workspace: Path,
    *,
    plan: TargetExecutionPlan,
) -> dict[str, Any]:
    runtime_workspace = runtime_workspace.resolve()
    if not runtime_workspace.is_dir() or runtime_workspace.is_symlink():
        raise ValueError("runtime workspace is missing or unsafe")
    report_path = runtime_workspace / "FORMAL_VERIFICATION_REPORT.json"
    report = KDPPFormalVerificationReport.model_validate(_load_object(report_path))
    if (
        report.status != "PASS"
        or report.certification_class != "CPU_FORMAL"
        or not report.formal_runtime_certification
    ):
        raise ValueError("runtime report is not CPU_FORMAL")
    preparation = _load_object(runtime_workspace / "preparation.json")
    expected_plan = {
        "run_id": plan.run_id,
        "source_revision": plan.source_revision,
        "config_sha256": plan.config_sha256,
        "prediction_length": plan.prediction_length,
        "seed": plan.seed,
        "samples_per_horizon": plan.samples_per_horizon,
        "rbf_gamma": plan.rbf_gamma,
        "quality_pseudocount": plan.quality_pseudocount,
        "psd_tolerance": plan.psd_tolerance,
        "game": plan.game,
    }
    if any(preparation.get(key) != value for key, value in expected_plan.items()):
        raise ValueError("runtime preparation differs from the control plan")
    certifier = Path(plan.kdpp.root) / "scripts/certify_kdpp_fixed_k_runtime.py"
    if preparation.get("certifier_sha256") != sha256_file(certifier):
        raise ValueError("runtime certifier differs from the controlled checkout")
    verify_inventory(
        runtime_workspace,
        "PREPARATION_SHA256SUMS",
        {
            "approved_history/history_manifest.json",
            "approved_history/item_ids.json",
            "approved_history/training.npz",
            "approved_history/SHA256SUMS",
            "history_approval.json",
            "certify_kdpp_fixed_k_runtime.py",
            "preparation.json",
        },
    )
    manifest, approval, _ = validate_history_bundle(
        runtime_workspace / "approved_history",
        runtime_workspace / "history_approval.json",
    )
    if manifest.game != plan.game or manifest.position != plan.position:
        raise ValueError("runtime history geometry differs from the control plan")
    actual_files = {
        path.relative_to(runtime_workspace).as_posix()
        for path in runtime_workspace.rglob("*")
        if path.is_file()
    }
    verify_inventory(
        runtime_workspace,
        "RUN_SHA256SUMS",
        actual_files - {"RUN_SHA256SUMS", "FORMAL_VERIFICATION_REPORT.json"},
    )
    pair = _load_object(runtime_workspace / "process_pair.json")
    rows = pair.get("process_records")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("runtime process pair must contain two records")
    pair_records = tuple(KDPPProcessRecord.model_validate(row) for row in rows)
    runtime_a = verify_runtime_directory(runtime_workspace / "process_A/runtime")
    runtime_b = verify_runtime_directory(runtime_workspace / "process_B/runtime")
    if pair_records != report.process_records:
        raise ValueError("formal report process records differ from process_pair.json")
    if pair_records[0].runtime_pid == pair_records[1].runtime_pid:
        raise ValueError("runtime process PIDs are not distinct")
    if runtime_a["prediction_sha256"] != runtime_b["prediction_sha256"]:
        raise ValueError("runtime prediction replay differs")
    if runtime_a["state_sha256"] != runtime_b["state_sha256"]:
        raise ValueError("runtime state replay differs")
    for label, runtime, record in zip(
        ("A", "B"),
        (runtime_a, runtime_b),
        pair_records,
        strict=True,
    ):
        root = runtime_workspace / f"process_{label}"
        seal = _load_object(root / "external_prediction_seal.json")
        if (
            seal.get("prediction_sha256") != runtime["prediction_sha256"]
            or seal.get("state_sha256") != runtime["state_sha256"]
            or seal.get("actuals_used") is not False
            or sha256_file(root / "external_prediction_seal.json")
            != record.prediction_seal_sha256
        ):
            raise ValueError("external prediction seal verification failed")
    if approval.reviewer != preparation.get("reviewer"):
        raise ValueError("runtime reviewer identity mismatch")
    return {
        "certification_class": report.certification_class,
        "formal_runtime_certification": True,
        "game": manifest.game,
        "position": manifest.position,
        "row_count": manifest.row_count,
        "reviewer": approval.reviewer,
        "runtime_pids": [record.runtime_pid for record in report.process_records],
        "prediction_sha256": runtime_a["prediction_sha256"],
        "state_sha256": runtime_a["state_sha256"],
        "report_sha256": sha256_file(report_path),
    }


