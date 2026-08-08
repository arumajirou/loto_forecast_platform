from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.runtime_evidence_gate import (
    FORMAL_CASE_NAMES,
    RuntimeEvidenceGateError,
    sha256_file,
    verify_campaign,
    verify_runtime_evidence_pair,
)
from tests.moirai2_campaign.p8c_evidence_fixtures import _campaign
from tests.moirai2_campaign.p8c_evidence_fixtures_core import (
    CONFIG_SHA,
    SOURCE_COMMIT,
    SOURCE_TREE,
    WEIGHT_SHA,
    _write_json,
)
from tests.moirai2_campaign.p8c_evidence_mutations import (
    _reseal,
    _rewrite_response_and_evidence,
)


def test_pair_verification_opens_p9_gate(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    cuda = _campaign(
        tmp_path / "cuda",
        campaign_id="cuda-run",
        runtime_lane="cuda13-experimental",
        device="cuda",
    )
    report = verify_runtime_evidence_pair(
        supported_campaign_dir=supported,
        cuda_campaign_dir=cuda,
        expected_source_commit=SOURCE_COMMIT,
    )
    assert report["status"] == "PASS"
    assert report["formal_case_count"] == 12
    assert report["provider_process_evidence_count"] == 24
    assert report["p9_oof_gate_open"] is True
    assert report["accuracy_claimed"] is False


def test_single_campaign_rechecks_all_cases(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    result = verify_campaign(
        campaign_dir=supported,
        expected_runtime_lane="supported-py311",
        expected_device="cpu",
        expected_source_commit=SOURCE_COMMIT,
    )
    assert len(result.cases) == 6
    assert {case.case_name for case in result.cases} == set(FORMAL_CASE_NAMES)
    assert all(not case.external_gpu_verified for case in result.cases)


def test_tampered_response_is_rejected_by_manifest(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    response_path = supported / "cases/draw-target-only/run-a/response.json"
    response_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeEvidenceGateError, match="SHA-256 mismatch"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_unlisted_extra_file_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    (supported / "untracked.txt").write_text("extra\n", encoding="utf-8")
    with pytest.raises(RuntimeEvidenceGateError, match="untracked artifacts"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_summary_self_claim_cannot_hide_failed_case(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    case_path = supported / "cases/draw-past-only/campaign_case_result.json"
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["status"] = "FAILED"
    _write_json(case_path, payload)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="case result did not pass"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_changed_quantile_is_rejected_after_reseal(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    response_path = supported / "cases/draw-target-only/run-b/response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["quantiles"]["q0.9"][0][0] += 1
    _write_json(response_path, response)
    evidence_path = supported / "cases/draw-target-only/run-b/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["response"] = response
    evidence["response_sha256"] = sha256_file(response_path)
    _write_json(evidence_path, evidence)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="reloaded predictions differ"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_non_monotonic_quantiles_are_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    for label in ("run-a", "run-b"):
        response_path = supported / f"cases/draw-target-only/{label}/response.json"
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["quantiles"]["q0.8"][0][0] = -100
        _write_json(response_path, response)
        evidence_path = supported / f"cases/draw-target-only/{label}/run_evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["response"] = response
        evidence["response_sha256"] = sha256_file(response_path)
        _write_json(evidence_path, evidence)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="not monotonic"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_cpu_fallback_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    response_path = supported / "cases/draw-target-only/run-a/response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["runtime_evidence"]["cpu_fallback"] = True
    _write_json(response_path, response)
    evidence_path = supported / "cases/draw-target-only/run-a/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["response"] = response
    evidence["response_sha256"] = sha256_file(response_path)
    _write_json(evidence_path, evidence)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="CPU fallback"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_cuda_external_pid_evidence_is_required(tmp_path: Path) -> None:
    cuda = _campaign(
        tmp_path / "cuda",
        campaign_id="cuda-run",
        runtime_lane="cuda13-experimental",
        device="cuda",
    )
    evidence_path = cuda / "cases/draw-target-only/run-a/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["external_gpu"]["external_pid_match"] = False
    _write_json(evidence_path, evidence)
    _reseal(cuda)
    with pytest.raises(RuntimeEvidenceGateError, match="external GPU summary differs"):
        verify_campaign(
            campaign_dir=cuda,
            expected_runtime_lane="cuda13-experimental",
            expected_device="cuda",
        )


def test_different_source_commits_block_p9(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    cuda = _campaign(
        tmp_path / "cuda",
        campaign_id="cuda-run",
        runtime_lane="cuda13-experimental",
        device="cuda",
        source_commit="e" * 40,
    )
    with pytest.raises(RuntimeEvidenceGateError, match="source commits differ"):
        verify_runtime_evidence_pair(
            supported_campaign_dir=supported,
            cuda_campaign_dir=cuda,
        )


def test_different_model_weights_block_p9(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    cuda = _campaign(
        tmp_path / "cuda",
        campaign_id="cuda-run",
        runtime_lane="cuda13-experimental",
        device="cuda",
    )
    preflight_path = cuda / "preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["lane_evidence"]["snapshot_files"]["model.safetensors"] = "f" * 64
    _write_json(preflight_path, preflight)
    _reseal(cuda)
    with pytest.raises(RuntimeEvidenceGateError, match="case model weight SHA"):
        verify_runtime_evidence_pair(
            supported_campaign_dir=supported,
            cuda_campaign_dir=cuda,
        )


def test_missing_lock_review_blocks_campaign(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    preflight_path = supported / "preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    del preflight["lane_evidence"]["lock_review"]
    _write_json(preflight_path, preflight)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="reviewed lock evidence"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )
