from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from loto.auto_campaign import api_coverage_pipeline as pipeline


def _fake_api_run(
    _project_root: Path,
    _config: Any,
    run_root: Path,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=resume)
    pd.DataFrame(
        [
            {
                "case.case_id": "base-h-5",
                "case.layer": "BaseAuto",
                "case.argument": "h",
                "case.expected": "PASS",
                "status": "EXECUTED",
            }
        ]
    ).to_parquet(run_root / "API_ARGUMENT_COVERAGE_RESULT.parquet", index=False)
    return {
        "schema_version": "all-auto-api-coverage-v1",
        "status": "PASS",
        "case_count": 1,
    }


def test_pipeline_integrates_coverage_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    monkeypatch.setattr(pipeline, "run_api_coverage", _fake_api_run)

    def fake_state_writer(
        *,
        output_dir: Path,
        api_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert api_results[0]["case.case_id"] == "base-h-5"
        output_dir.mkdir(parents=True)
        state = {
            "schema_version": "all-auto-coverage-state-v1",
            "status": "VERIFIED",
            "gpu_runtime_status": "EXECUTION_PENDING",
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(state),
            encoding="utf-8",
        )
        return state

    monkeypatch.setattr(pipeline, "write_coverage_state_bundle", fake_state_writer)
    result = pipeline.run_api_coverage_pipeline(
        tmp_path,
        object(),
        run_root,
    )

    assert result["status"] == "PASS"
    assert result["verification_status"] == "VERIFIED"
    assert result["coverage_state_status"] == "VERIFIED"
    assert result["gpu_runtime_status"] == "EXECUTION_PENDING"
    assert result["coverage_state_path"] == "coverage-state/manifest.json"
    assert (run_root / "coverage-state" / "manifest.json").is_file()
    assert (run_root / "SHA256SUMS").is_file()
    assert pipeline.load_integrated_manifest(run_root) == result


def test_pipeline_records_resolver_failure_without_losing_api_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    monkeypatch.setattr(pipeline, "run_api_coverage", _fake_api_run)

    def fail_state_writer(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("constructor inventory mismatch")

    monkeypatch.setattr(pipeline, "write_coverage_state_bundle", fail_state_writer)
    result = pipeline.run_api_coverage_pipeline(
        tmp_path,
        object(),
        run_root,
    )

    assert result["status"] == "PARTIAL"
    assert result["verification_status"] == "FAILED"
    assert result["coverage_state_status"] == "FAILED"
    assert result["gpu_runtime_status"] == "EXECUTION_PENDING"
    assert result["coverage_state_path"] == "coverage_state_failure.json"
    assert (run_root / "API_ARGUMENT_COVERAGE_RESULT.parquet").is_file()
    failure = json.loads(
        (run_root / "coverage_state_failure.json").read_text(encoding="utf-8")
    )
    assert failure["failed_phase"] == "coverage_state_resolution"
    assert failure["error_type"] == "RuntimeError"
    assert "inventory mismatch" in failure["error"]


def test_successful_resume_removes_stale_failure_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    stale = run_root / "coverage_state_failure.json"
    stale.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pipeline, "run_api_coverage", _fake_api_run)

    def fake_state_writer(
        *,
        output_dir: Path,
        api_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert api_results
        output_dir.mkdir(parents=True)
        return {
            "schema_version": "all-auto-coverage-state-v1",
            "status": "PARTIALLY_VERIFIED",
            "gpu_runtime_status": "EXECUTION_PENDING",
        }

    monkeypatch.setattr(pipeline, "write_coverage_state_bundle", fake_state_writer)
    result = pipeline.run_api_coverage_pipeline(
        tmp_path,
        object(),
        run_root,
        resume=True,
    )

    assert result["status"] == "PASS"
    assert result["verification_status"] == "PARTIALLY_VERIFIED"
    assert not stale.exists()


def test_load_integrated_manifest_rejects_missing_contract_fields(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "manifest.json").write_text(
        json.dumps({"status": "PASS"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing fields"):
        pipeline.load_integrated_manifest(run_root)
