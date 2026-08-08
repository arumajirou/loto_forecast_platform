from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_campaign import verify_campaign
from loto.moirai2_campaign.runtime_evidence_common import (
    CampaignVerification,
    RuntimeEvidenceGateError,
    sha256_file,
    sha256_payload,
)
from loto.moirai2_campaign.runtime_evidence_prediction import _require_equal


def _cross_lane_prediction_evidence(
    supported: CampaignVerification,
    cuda: CampaignVerification,
) -> list[dict[str, Any]]:
    cuda_by_name = {case.case_name: case for case in cuda.cases}
    rows: list[dict[str, Any]] = []
    for supported_case in supported.cases:
        cuda_case = cuda_by_name[supported_case.case_name]
        rows.append(
            {
                "case": supported_case.case_name,
                "supported_prediction_sha256": supported_case.prediction_sha256,
                "cuda_prediction_sha256": cuda_case.prediction_sha256,
                "exact_cross_lane_match": (
                    supported_case.prediction_sha256 == cuda_case.prediction_sha256
                ),
            }
        )
    return rows


def verify_runtime_evidence_pair(
    *,
    supported_campaign_dir: Path,
    cuda_campaign_dir: Path,
    expected_source_commit: str | None = None,
) -> dict[str, Any]:
    supported_root = supported_campaign_dir.resolve()
    cuda_root = cuda_campaign_dir.resolve()
    if supported_root == cuda_root:
        raise RuntimeEvidenceGateError("supported and CUDA campaign directories must differ")
    supported = verify_campaign(
        campaign_dir=supported_root,
        expected_runtime_lane="supported-py311",
        expected_device="cpu",
        expected_source_commit=expected_source_commit,
    )
    cuda = verify_campaign(
        campaign_dir=cuda_root,
        expected_runtime_lane="cuda13-experimental",
        expected_device="cuda",
        expected_source_commit=expected_source_commit,
    )
    _require_equal(
        supported.source_commit,
        cuda.source_commit,
        "CPU and CUDA source commits differ",
    )
    _require_equal(
        supported.source_tree,
        cuda.source_tree,
        "CPU and CUDA source trees differ",
    )
    _require_equal(
        supported.snapshot_config_sha256,
        cuda.snapshot_config_sha256,
        "CPU and CUDA snapshot config SHA values differ",
    )
    _require_equal(
        supported.snapshot_weight_sha256,
        cuda.snapshot_weight_sha256,
        "CPU and CUDA snapshot weight SHA values differ",
    )
    supported_artifact = {
        (case.model_revision, case.config_sha256, case.weight_sha256) for case in supported.cases
    }
    cuda_artifact = {
        (case.model_revision, case.config_sha256, case.weight_sha256) for case in cuda.cases
    }
    _require_equal(supported_artifact, cuda_artifact, "CPU and CUDA model identities differ")
    cross_lane = _cross_lane_prediction_evidence(supported, cuda)
    report = {
        "schema_version": "moirai2-p8c-runtime-evidence-gate-v1",
        "status": "PASS",
        "phase": "P8C_RUNTIME_EVIDENCE_GATE",
        "source_commit": supported.source_commit,
        "source_tree": supported.source_tree,
        "supported_campaign": supported.as_dict(),
        "cuda_campaign": cuda.as_dict(),
        "cross_lane_prediction_evidence": cross_lane,
        "formal_campaign_count": 2,
        "formal_case_count": 12,
        "provider_process_evidence_count": 24,
        "same_model_artifact_across_lanes": True,
        "same_source_across_lanes": True,
        "all_manifests_verified": True,
        "all_native_quantiles_verified": True,
        "all_reload_pairs_verified": True,
        "all_cuda_external_gpu_evidence_verified": True,
        "accuracy_claimed": False,
        "oof_executed": False,
        "holdout_executed": False,
        "prospective_executed": False,
        "p9_oof_gate_open": True,
    }
    report["report_payload_sha256"] = sha256_payload(report)
    return report


def write_sha256_manifest(root: Path, output_path: Path) -> None:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != output_path.resolve()
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    output_path.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
