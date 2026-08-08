from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.runtime_evidence_gate import (
    RuntimeEvidenceGateError,
    sha256_file,
    verify_campaign,
    verify_runtime_evidence_pair,
)
from tests.moirai2_campaign.p8c_evidence_fixtures import _campaign
from tests.moirai2_campaign.p8c_evidence_fixtures_core import (
    _write_json,
)
from tests.moirai2_campaign.p8c_evidence_mutations import (
    _reseal,
)


def test_cuda_gpu_uuid_is_required(tmp_path: Path) -> None:
    cuda = _campaign(
        tmp_path / "cuda",
        campaign_id="cuda-run",
        runtime_lane="cuda13-experimental",
        device="cuda",
    )
    evidence_path = cuda / "cases/draw-target-only/run-a/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["external_gpu"]["gpu_uuid"] = ""
    _write_json(evidence_path, evidence)
    certification_path = cuda / "cases/draw-target-only/certification.json"
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    certification["run_a"]["external_gpu"]["gpu_uuid"] = ""
    _write_json(certification_path, certification)
    result_path = cuda / "cases/draw-target-only/campaign_case_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["certification"] = certification
    _write_json(result_path, result)
    _reseal(cuda)
    with pytest.raises(RuntimeEvidenceGateError, match="external GPU summary differs"):
        verify_campaign(
            campaign_dir=cuda,
            expected_runtime_lane="cuda13-experimental",
            expected_device="cuda",
        )


def test_provider_pid_release_is_required(tmp_path: Path) -> None:
    cuda = _campaign(
        tmp_path / "cuda",
        campaign_id="cuda-run",
        runtime_lane="cuda13-experimental",
        device="cuda",
    )
    evidence_path = cuda / "cases/draw-target-only/run-a/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["external_gpu"]["pid_absent_after_exit"] = False
    _write_json(evidence_path, evidence)
    certification_path = cuda / "cases/draw-target-only/certification.json"
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    certification["run_a"]["external_gpu"]["pid_absent_after_exit"] = False
    _write_json(certification_path, certification)
    result_path = cuda / "cases/draw-target-only/campaign_case_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["certification"] = certification
    _write_json(result_path, result)
    _reseal(cuda)
    with pytest.raises(RuntimeEvidenceGateError, match="external GPU summary differs"):
        verify_campaign(
            campaign_dir=cuda,
            expected_runtime_lane="cuda13-experimental",
            expected_device="cuda",
        )


def test_lock_review_lane_mismatch_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    preflight_path = supported / "preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["lane_evidence"]["lock_review"]["runtime_lane"] = "wrong-lane"
    _write_json(preflight_path, preflight)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="reviewed lock runtime lane"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_source_tree_mismatch_blocks_pair(tmp_path: Path) -> None:
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
    config_path = cuda / "campaign_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["source_identity"]["tree_sha"] = "f" * 40
    _write_json(config_path, config)
    launch_path = cuda / "P8C_LAUNCH_EVIDENCE.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["source_identity"] = config["source_identity"]
    launch["campaign_config_sha256"] = sha256_file(config_path)
    _write_json(launch_path, launch)
    _reseal(cuda)
    with pytest.raises(RuntimeEvidenceGateError, match="source trees differ"):
        verify_runtime_evidence_pair(
            supported_campaign_dir=supported,
            cuda_campaign_dir=cuda,
        )


def test_snapshot_config_mismatch_blocks_campaign(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    preflight_path = supported / "preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["lane_evidence"]["snapshot_files"]["config.json"] = "f" * 64
    _write_json(preflight_path, preflight)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="case model config SHA"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_selected_case_order_is_fixed(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    config_path = supported / "campaign_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["selected_cases"] = list(reversed(config["selected_cases"]))
    _write_json(config_path, config)
    launch_path = supported / "P8C_LAUNCH_EVIDENCE.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["campaign_config_sha256"] = sha256_file(config_path)
    _write_json(launch_path, launch)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="selected cases differ"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_request_seed_is_fixed(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    request_path = supported / "requests/draw-target-only.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["seed"] = 2
    _write_json(request_path, request)
    case_path = supported / "cases/draw-target-only/campaign_case_result.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["request_sha256"] = sha256_file(request_path)
    _write_json(case_path, case)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="request seed differs"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )
