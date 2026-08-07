from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from loto.auto_campaign import api_coverage_pipeline as pipeline
from loto.auto_campaign.coverage_verification import (
    verify_coverage_state_artifacts,
    verify_run_with_coverage,
)
from loto.auto_campaign.persistence import write_json, write_sha256s


def _write_api_root_files(run_root: Path) -> None:
    pd.DataFrame([{"case_id": "base-h-5"}]).to_parquet(
        run_root / "API_ARGUMENT_COVERAGE_PLAN.parquet",
        index=False,
    )
    result = pd.DataFrame(
        [
            {
                "case.case_id": "base-h-5",
                "case.layer": "BaseAuto",
                "case.argument": "h",
                "status": "EXECUTED",
            }
        ]
    )
    result.to_csv(run_root / "API_ARGUMENT_COVERAGE_RESULT.csv", index=False)
    result.to_parquet(run_root / "API_ARGUMENT_COVERAGE_RESULT.parquet", index=False)
    write_json(run_root / "failures.json", [])


def _successful_run(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    run_root = tmp_path / "run"
    run_root.mkdir()
    _write_api_root_files(run_root)

    coverage_root = run_root / "coverage-state"
    coverage_root.mkdir()
    constructor_rows = [
        {
            "name": f"AutoModel{index:02d}",
            "verification_status": "VERIFIED",
        }
        for index in range(36)
    ]
    resolved_rows = [
        {
            "layer": "BaseAuto",
            "argument": "h",
            "verification_status": "VERIFIED",
        },
        {
            "layer": "BaseAuto",
            "argument": "config",
            "verification_status": "VERIFIED",
        },
    ]
    summary = {
        "overall_status": "VERIFIED",
        "argument_count": 2,
        "verification_status_counts": {"VERIFIED": 2},
        "verified_arguments": 2,
        "pending_arguments": 0,
        "partially_verified_arguments": 0,
        "failed_arguments": 0,
    }
    nested_manifest = {
        "schema_version": "all-auto-coverage-state-v1",
        "status": "VERIFIED",
        "constructor_model_count": 36,
        "constructor_status_counts": {"VERIFIED": 36},
        "api_result_count": 1,
        "gpu_runtime_status": "EXECUTION_PENDING",
    }

    write_json(
        coverage_root / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.json",
        constructor_rows,
    )
    constructor_frame = pd.DataFrame(constructor_rows)
    constructor_frame.to_csv(
        coverage_root / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.csv",
        index=False,
    )
    constructor_frame.to_parquet(
        coverage_root / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.parquet",
        index=False,
    )
    write_json(
        coverage_root / "API_ARGUMENT_COVERAGE_RESOLVED.json",
        resolved_rows,
    )
    resolved_frame = pd.DataFrame(resolved_rows)
    resolved_frame.to_csv(
        coverage_root / "API_ARGUMENT_COVERAGE_RESOLVED.csv",
        index=False,
    )
    resolved_frame.to_parquet(
        coverage_root / "API_ARGUMENT_COVERAGE_RESOLVED.parquet",
        index=False,
    )
    write_json(coverage_root / "COVERAGE_SUMMARY.json", summary)
    write_json(coverage_root / "manifest.json", nested_manifest)
    write_sha256s(coverage_root)

    manifest = {
        "schema_version": "all-auto-api-coverage-v1",
        "status": "PASS",
        "planned_tasks": 0,
        "coverage_state_schema_version": "all-auto-coverage-state-v1",
        "coverage_state_status": "VERIFIED",
        "verification_status": "VERIFIED",
        "coverage_state_path": "coverage-state/manifest.json",
        "gpu_runtime_status": "EXECUTION_PENDING",
        "coverage_state": nested_manifest,
    }
    write_json(run_root / "manifest.json", manifest)
    write_sha256s(run_root)
    return run_root, manifest


def _failed_run(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    run_root = tmp_path / "failed-run"
    run_root.mkdir()
    _write_api_root_files(run_root)
    failure = {
        "schema_version": "all-auto-coverage-state-failure-v1",
        "status": "FAILED",
        "failed_phase": "coverage_state_resolution",
        "error_type": "RuntimeError",
        "error": "constructor inventory mismatch",
        "traceback": "traceback",
        "gpu_runtime_status": "EXECUTION_PENDING",
    }
    write_json(run_root / "coverage_state_failure.json", failure)
    manifest = {
        "schema_version": "all-auto-api-coverage-v1",
        "status": "PARTIAL",
        "planned_tasks": 0,
        "coverage_state_schema_version": failure["schema_version"],
        "coverage_state_status": "FAILED",
        "verification_status": "FAILED",
        "coverage_state_path": "coverage_state_failure.json",
        "gpu_runtime_status": "EXECUTION_PENDING",
        "coverage_state": failure,
    }
    write_json(run_root / "manifest.json", manifest)
    write_sha256s(run_root)
    return run_root, manifest


def test_successful_coverage_state_bundle_verifies(tmp_path: Path) -> None:
    run_root, manifest = _successful_run(tmp_path)

    result = verify_coverage_state_artifacts(run_root, manifest)

    assert result["status"] == "PASS"
    assert result["artifact_mode"] == "coverage-state-bundle"
    assert result["constructor_model_count"] == 36
    assert result["resolved_argument_count"] == 2
    assert result["api_result_count"] == 1
    assert result["failures"] == []


def test_nested_sha256_tampering_fails_verification(tmp_path: Path) -> None:
    run_root, manifest = _successful_run(tmp_path)
    target = run_root / "coverage-state" / "COVERAGE_SUMMARY.json"
    target.write_text("{}\n", encoding="utf-8")

    result = verify_coverage_state_artifacts(run_root, manifest)

    assert result["status"] == "FAIL"
    assert any("SHA256" in failure and "mismatch" in failure for failure in result["failures"])


def test_failed_resolver_evidence_can_be_internally_consistent(tmp_path: Path) -> None:
    run_root, manifest = _failed_run(tmp_path)

    result = verify_coverage_state_artifacts(run_root, manifest)

    assert result["status"] == "PASS"
    assert result["coverage_state_status"] == "FAILED"
    assert result["artifact_mode"] == "failure-evidence"


def test_gpu_status_cannot_be_promoted_without_runtime_evidence(tmp_path: Path) -> None:
    run_root, manifest = _successful_run(tmp_path)
    manifest["gpu_runtime_status"] = "VERIFIED"

    result = verify_coverage_state_artifacts(run_root, manifest)

    assert result["status"] == "FAIL"
    assert any("GPU boundary" in failure for failure in result["failures"])


def test_coverage_state_path_must_remain_inside_run_root(tmp_path: Path) -> None:
    run_root, manifest = _successful_run(tmp_path)
    manifest["coverage_state_path"] = "../outside/manifest.json"

    result = verify_coverage_state_artifacts(run_root, manifest)

    assert result["status"] == "FAIL"
    assert any("unsafe coverage_state_path" in failure for failure in result["failures"])


def test_standard_verify_wrapper_includes_coverage_report(tmp_path: Path) -> None:
    run_root, _manifest = _successful_run(tmp_path)

    result = verify_run_with_coverage(run_root)

    assert result["status"] == "PASS"
    assert result["coverage_state_verification"]["status"] == "PASS"
    report = json.loads(
        (run_root / "VERIFICATION_REPORT.json").read_text(encoding="utf-8")
    )
    assert report["coverage_state_verification"]["constructor_model_count"] == 36
    assert (run_root / "SHA256SUMS").is_file()


def test_pipeline_removes_partial_coverage_directory_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "pipeline-run"

    def fake_api_run(
        _project_root: Path,
        _config: Any,
        output: Path,
        *,
        resume: bool = False,
    ) -> dict[str, Any]:
        output.mkdir(parents=True, exist_ok=resume)
        _write_api_root_files(output)
        return {"schema_version": "all-auto-api-coverage-v1", "status": "PASS"}

    def partial_writer(
        *,
        output_dir: Path,
        api_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert api_results
        output_dir.mkdir(parents=True)
        (output_dir / "partial.json").write_text("{}", encoding="utf-8")
        raise RuntimeError("resolver failed after partial write")

    monkeypatch.setattr(pipeline, "run_api_coverage", fake_api_run)
    monkeypatch.setattr(pipeline, "write_coverage_state_bundle", partial_writer)

    result = pipeline.run_api_coverage_pipeline(tmp_path, object(), run_root)

    assert result["status"] == "PARTIAL"
    assert not (run_root / "coverage-state").exists()
    assert (run_root / "coverage_state_failure.json").is_file()
