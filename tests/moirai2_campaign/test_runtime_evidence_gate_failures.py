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
    SOURCE_COMMIT,
    _write_json,
)
from tests.moirai2_campaign.p8c_evidence_mutations import (
    _reseal,
    _rewrite_response_and_evidence,
)


def test_same_campaign_directory_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    with pytest.raises(RuntimeEvidenceGateError, match="must differ"):
        verify_runtime_evidence_pair(
            supported_campaign_dir=supported,
            cuda_campaign_dir=supported,
        )


def test_prepare_only_campaign_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    config_path = supported / "campaign_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["prepare_only"] = True
    _write_json(config_path, config)
    launch_path = supported / "P8C_LAUNCH_EVIDENCE.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["campaign_config_sha256"] = sha256_file(config_path)
    _write_json(launch_path, launch)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="prepare-only"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_missing_source_identity_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    config_path = supported / "campaign_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["source_identity"]
    _write_json(config_path, config)
    launch_path = supported / "P8C_LAUNCH_EVIDENCE.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["campaign_config_sha256"] = sha256_file(config_path)
    _write_json(launch_path, launch)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="source identity is missing"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_dirty_source_identity_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    config_path = supported / "campaign_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["source_identity"]["worktree_clean"] = False
    _write_json(config_path, config)
    launch_path = supported / "P8C_LAUNCH_EVIDENCE.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["source_identity"] = config["source_identity"]
    launch["campaign_config_sha256"] = sha256_file(config_path)
    _write_json(launch_path, launch)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="was not clean"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_expected_source_commit_mismatch_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    with pytest.raises(RuntimeEvidenceGateError, match="differs from expected"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
            expected_source_commit="f" * 40,
        )


def test_missing_native_quantile_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    for label in ("run-a", "run-b"):
        response_path = supported / f"cases/draw-target-only/{label}/response.json"
        response = json.loads(response_path.read_text(encoding="utf-8"))
        del response["quantiles"]["q0.9"]
        _rewrite_response_and_evidence(
            supported,
            case_name="draw-target-only",
            label=label,
            response=response,
        )
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="quantile keys differ"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_point_forecast_must_equal_median_quantile(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    for label in ("run-a", "run-b"):
        response_path = supported / f"cases/draw-target-only/{label}/response.json"
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["point_forecast"][0][0] += 1
        _rewrite_response_and_evidence(
            supported,
            case_name="draw-target-only",
            label=label,
            response=response,
        )
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="does not equal q0.5"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_non_finite_prediction_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    for label in ("run-a", "run-b"):
        response_path = supported / f"cases/draw-target-only/{label}/response.json"
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["quantiles"]["q0.1"][0][0] = float("nan")
        _rewrite_response_and_evidence(
            supported,
            case_name="draw-target-only",
            label=label,
            response=response,
        )
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="non-finite"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )


def test_same_reload_pid_is_rejected(tmp_path: Path) -> None:
    supported = _campaign(
        tmp_path / "supported",
        campaign_id="cpu-run",
        runtime_lane="supported-py311",
        device="cpu",
    )
    case_dir = supported / "cases/draw-target-only"
    response_a = json.loads((case_dir / "run-a/response.json").read_text(encoding="utf-8"))
    response_b = json.loads((case_dir / "run-b/response.json").read_text(encoding="utf-8"))
    pid = response_a["runtime_evidence"]["process_id"]
    response_b["runtime_evidence"]["process_id"] = pid
    response_b["gpu_evidence"]["provider_pid"] = pid
    _rewrite_response_and_evidence(
        supported,
        case_name="draw-target-only",
        label="run-b",
        response=response_b,
    )
    evidence_path = case_dir / "run-b/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["process_id"] = pid
    evidence["external_gpu"]["provider_pid"] = pid
    _write_json(evidence_path, evidence)
    certification_path = case_dir / "certification.json"
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    certification["prediction_comparison"]["process_b"] = pid
    certification["run_b"]["process_id"] = pid
    certification["run_b"]["external_gpu"]["provider_pid"] = pid
    _write_json(certification_path, certification)
    result_path = case_dir / "campaign_case_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["certification"] = certification
    _write_json(result_path, result)
    _reseal(supported)
    with pytest.raises(RuntimeEvidenceGateError, match="not distinct"):
        verify_campaign(
            campaign_dir=supported,
            expected_runtime_lane="supported-py311",
            expected_device="cpu",
        )
