from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from loto.moirai2_campaign.target_execution_common import (
    CUDA_LANE,
    LANE_DEVICES,
    MANIFEST_FILENAME,
    SHA_FILENAME,
    SUPPORTED_LANE,
    TargetExecutionError,
    load_json_object,
    sha256_file,
    verify_sha256_manifest,
)


def _require_lane(runtime_lane: str) -> None:
    if runtime_lane not in LANE_DEVICES:
        raise TargetExecutionError(f"unsupported runtime lane: {runtime_lane}")


def _timezone_aware(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_candidate_artifact(
    artifact_dir: Path,
    *,
    runtime_lane: str,
) -> dict[str, Any]:
    _require_lane(runtime_lane)
    root = artifact_dir.resolve()
    manifest = verify_sha256_manifest(root)
    result = load_json_object(root / "CANDIDATE_RESULT.json")
    report = load_json_object(root / "LOCK_REVIEW_REPORT.json")
    lock_path = root / "candidate-project" / "uv.lock"
    if not lock_path.is_file():
        raise TargetExecutionError("candidate uv.lock is missing")
    if result.get("status") != "PASS" or result.get("review_status") != "PASS":
        raise TargetExecutionError("candidate result or static review did not pass")
    if result.get("runtime_lane") != runtime_lane:
        raise TargetExecutionError("candidate runtime lane differs")
    if int(result.get("violation_count", -1)) != 0:
        raise TargetExecutionError("candidate contains static review violations")
    if report.get("status") != "PASS" or report.get("runtime_lane") != runtime_lane:
        raise TargetExecutionError("candidate review report differs")
    lock_sha = sha256_file(lock_path)
    if result.get("candidate_lock_sha256") != lock_sha:
        raise TargetExecutionError("candidate lock SHA-256 differs")
    return {
        "runtime_lane": runtime_lane,
        "candidate_lock_sha256": lock_sha,
        "candidate_result_sha256": sha256_file(root / "CANDIDATE_RESULT.json"),
        "review_report_sha256": sha256_file(root / "LOCK_REVIEW_REPORT.json"),
        "warning_count": int(result.get("warning_count", 0)),
        "package_count": int(result.get("package_count", 0)),
        "manifest": manifest,
    }


def validate_installation_artifact(
    artifact_dir: Path,
    *,
    runtime_lane: str,
    candidate_summary: Mapping[str, Any],
) -> dict[str, Any]:
    _require_lane(runtime_lane)
    root = artifact_dir.resolve()
    manifest = verify_sha256_manifest(root)
    evidence = load_json_object(root / "INSTALLATION_EVIDENCE.json")
    if evidence.get("status") != "INSTALLED":
        raise TargetExecutionError("reviewed lock was not installed")
    if evidence.get("runtime_lane") != runtime_lane:
        raise TargetExecutionError("installation runtime lane differs")
    if evidence.get("apply_requested") is not True:
        raise TargetExecutionError("installation evidence is not an applied install")
    expected_lock = str(candidate_summary.get("candidate_lock_sha256", ""))
    if evidence.get("candidate_lock_sha256") != expected_lock:
        raise TargetExecutionError("installation candidate lock SHA-256 differs")
    reviewer = str(evidence.get("reviewer", "")).strip()
    reviewed_at = str(evidence.get("reviewed_at", ""))
    if not reviewer or not _timezone_aware(reviewed_at):
        raise TargetExecutionError("human reviewer or timezone-aware review time is missing")
    installed_review = evidence.get("installed_review")
    if not isinstance(installed_review, dict):
        raise TargetExecutionError("installed review evidence is missing")
    if installed_review.get("runtime_lane") != runtime_lane:
        raise TargetExecutionError("installed review runtime lane differs")
    if installed_review.get("lock_sha256") != expected_lock:
        raise TargetExecutionError("installed review lock SHA-256 differs")
    return {
        "runtime_lane": runtime_lane,
        "candidate_lock_sha256": expected_lock,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "installation_evidence_sha256": sha256_file(root / "INSTALLATION_EVIDENCE.json"),
        "manifest": manifest,
    }


def validate_campaign_artifact(
    artifact_dir: Path,
    *,
    runtime_lane: str,
    source_commit: str,
) -> dict[str, Any]:
    _require_lane(runtime_lane)
    from loto.moirai2_campaign.runtime_evidence_gate import verify_campaign

    verification = verify_campaign(
        campaign_dir=artifact_dir,
        expected_runtime_lane=runtime_lane,
        expected_device=LANE_DEVICES[runtime_lane],
        expected_source_commit=source_commit,
    )
    return {
        "runtime_lane": runtime_lane,
        "campaign_id": verification.campaign_id,
        "source_commit": verification.source_commit,
        "source_tree": verification.source_tree,
        "lock_sha256": verification.lock_sha256,
        "snapshot_config_sha256": verification.snapshot_config_sha256,
        "snapshot_weight_sha256": verification.snapshot_weight_sha256,
        "case_count": len(verification.cases),
        "provider_process_count": len(verification.cases) * 2,
    }


def validate_pair_artifact(
    artifact_dir: Path,
    *,
    supported_campaign_dir: Path,
    cuda_campaign_dir: Path,
    source_commit: str,
) -> dict[str, Any]:
    root = artifact_dir.resolve()
    manifest = verify_sha256_manifest(root)
    retained = load_json_object(root / "P8C_RUNTIME_EVIDENCE_REPORT.json")
    from loto.moirai2_campaign.runtime_evidence_gate import (
        verify_runtime_evidence_pair,
    )

    recomputed = verify_runtime_evidence_pair(
        supported_campaign_dir=supported_campaign_dir,
        cuda_campaign_dir=cuda_campaign_dir,
        expected_source_commit=source_commit,
    )
    if sha256_payload(retained) != sha256_payload(recomputed):
        raise TargetExecutionError("retained and recomputed P8C reports differ")
    if retained.get("status") != "PASS" or retained.get("p9_oof_gate_open") is not True:
        raise TargetExecutionError("P8C pair verification did not open the P9 gate")
    for key, expected in (
        ("formal_campaign_count", 2),
        ("formal_case_count", 12),
        ("provider_process_evidence_count", 24),
    ):
        if int(retained.get(key, -1)) != expected:
            raise TargetExecutionError(f"P8C pair count differs: {key}")
    return {
        "source_commit": source_commit,
        "formal_campaign_count": 2,
        "formal_case_count": 12,
        "provider_process_evidence_count": 24,
        "p9_oof_gate_open": True,
        "report_sha256": sha256_file(root / "P8C_RUNTIME_EVIDENCE_REPORT.json"),
        "manifest": manifest,
    }
