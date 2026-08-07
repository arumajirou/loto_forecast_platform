from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import promotion_gate as gate
from loto.auto_campaign.contracts import CampaignConfig, CampaignStage, ResourceConfig
from loto.auto_campaign.persistence import write_json, write_sha256s


def _config(tmp_path: Path, *, gpu: bool) -> CampaignConfig:
    resources = ResourceConfig(
        accelerator="gpu" if gpu else "cpu",
        gpus_per_trial=0.25 if gpu else 0.0,
        logical_workers=8,
        gpu_concurrency=1,
    )
    return CampaignConfig(
        data_path=tmp_path / "data.parquet",
        output_root=tmp_path / "artifacts",
        resources=resources,
    )


def _coverage_run(tmp_path: Path) -> Path:
    root = tmp_path / "coverage"
    root.mkdir()
    manifest = {
        "status": "PASS",
        "coverage_state_status": "VERIFIED",
        "verification_status": "VERIFIED",
        "gpu_runtime_status": "EXECUTION_PENDING",
    }
    report = {
        "status": "PASS",
        "coverage_state_verification": {"status": "PASS", "failures": []},
    }
    write_json(root / "manifest.json", manifest)
    write_json(root / "VERIFICATION_REPORT.json", report)
    write_sha256s(root)
    return root


def _runtime_certification(*, cpu_fallback: bool = False) -> dict[str, Any]:
    runtime = {
        "parameter_device": "cuda:0",
        "trainer_root_device": "cuda:0",
        "cuda_memory_allocated": 1024,
        "cuda_memory_reserved": 2048,
        "cuda_peak_memory_allocated": 4096,
    }
    gpu = {"gpu_pid_verified": True, "pid": 1234, "rows": [{"used_memory_mib": 512}]}
    return {
        "status": "PASS",
        "require_gpu": True,
        "formal_cuda_training_evidence": True,
        "cuda_pre_save_inference_evidence": True,
        "cuda_reload_inference_evidence": not cpu_fallback,
        "cuda_execution_evidence": not cpu_fallback,
        "cpu_fallback": cpu_fallback,
        "loaded": True,
        "predicted": True,
        "shape_match": True,
        "key_match": True,
        "finite": True,
        "prediction_match": True,
        "state_before_finite": True,
        "state_after_finite": True,
        "training_evidence": {"worker_pid": 5678, "device": "cuda:0"},
        "runtime_pre_save_inference": runtime,
        "runtime_reload_inference": (
            runtime if not cpu_fallback else {**runtime, "parameter_device": "cpu"}
        ),
        "gpu_pre_save_inference": gpu,
        "gpu_reload_inference": (
            gpu if not cpu_fallback else {"gpu_pid_verified": False, "rows": []}
        ),
    }


def _runtime_run(tmp_path: Path, *, failed_index: int | None = None) -> Path:
    root = tmp_path / "runtime"
    root.mkdir()
    reports: list[dict[str, Any]] = []
    for index in range(36):
        failed = index == failed_index
        reports.append(
            {
                "model_id": f"nf-auto-{index:02d}",
                "status": "SUCCEEDED",
                "certification_status": "RUNTIME_CERTIFIED",
                "runtime_certification": _runtime_certification(cpu_fallback=failed),
            }
        )
    write_json(
        root / "campaign_report.json",
        {
            "schema_version": "1.2.0",
            "status": "SUCCEEDED",
            "certification_status": "RUNTIME_CERTIFIED",
            "started_model_count": 36,
            "succeeded_model_count": 36,
            "runtime_certified_model_count": 36,
            "failed_model_count": 0,
            "reports": reports,
        },
    )
    return root


def _patch_coverage_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "verify_sha256s", lambda _root: [])
    monkeypatch.setattr(
        gate,
        "verify_coverage_state_artifacts",
        lambda _root, _manifest: {"status": "PASS", "failures": []},
    )


def test_cpu_stage_passes_with_verified_coverage_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_coverage_verification(monkeypatch)

    result = gate.evaluate_promotion_gate(
        config=_config(tmp_path, gpu=False),
        target_stage=CampaignStage.HPO,
        coverage_run=_coverage_run(tmp_path),
    )

    assert result["status"] == "PASS"
    assert result["requires_gpu_runtime"] is False
    assert result["runtime_evidence"] is None
    assert result["failures"] == []


def test_gpu_stage_blocks_without_runtime_campaign(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_coverage_verification(monkeypatch)

    result = gate.evaluate_promotion_gate(
        config=_config(tmp_path, gpu=True),
        target_stage=CampaignStage.OOF,
        coverage_run=_coverage_run(tmp_path),
        runtime_run=None,
    )

    assert result["status"] == "BLOCKED"
    assert result["requires_gpu_runtime"] is True
    assert any("requires --runtime-run" in failure for failure in result["failures"])


def test_gpu_stage_passes_with_complete_36_model_runtime_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_coverage_verification(monkeypatch)

    result = gate.evaluate_promotion_gate(
        config=_config(tmp_path, gpu=True),
        target_stage=CampaignStage.PROSPECTIVE,
        coverage_run=_coverage_run(tmp_path),
        runtime_run=_runtime_run(tmp_path),
    )

    assert result["status"] == "PASS"
    assert result["runtime_evidence"]["observed_model_count"] == 36
    assert result["runtime_evidence"]["failed_models"] == []


def test_one_cpu_fallback_blocks_entire_gpu_campaign(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_coverage_verification(monkeypatch)

    result = gate.evaluate_promotion_gate(
        config=_config(tmp_path, gpu=True),
        target_stage=CampaignStage.HOLDOUT,
        coverage_run=_coverage_run(tmp_path),
        runtime_run=_runtime_run(tmp_path, failed_index=7),
    )

    assert result["status"] == "BLOCKED"
    assert result["runtime_evidence"]["failed_models"] == ["nf-auto-07"]
    assert any("no_cpu_fallback" in failure for failure in result["failures"])


def test_nongated_stage_is_not_applicable(tmp_path: Path) -> None:
    result = gate.evaluate_promotion_gate(
        config=_config(tmp_path, gpu=True),
        target_stage=CampaignStage.SMOKE,
        coverage_run=None,
    )

    assert result["status"] == "NOT_APPLICABLE"
    assert result["failures"] == []


def test_blocked_wrapper_writes_sidecar_and_does_not_call_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        gate,
        "evaluate_promotion_gate",
        lambda **_kwargs: {
            "schema_version": "all-auto-promotion-gate-v1",
            "status": "BLOCKED",
            "target_stage": "hpo",
            "failures": ["missing evidence"],
        },
    )
    called = False

    def runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"status": "PASS"}

    run_root = tmp_path / "hpo-run"
    result = gate.run_stage_with_promotion_gate(
        runner=runner,
        project_root=tmp_path,
        config=_config(tmp_path, gpu=False),
        run_root=run_root,
        target_stage=CampaignStage.HPO,
        source_run=None,
        coverage_run=None,
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "BLOCKED"
    assert called is False
    sidecar = tmp_path / "hpo-run.PROMOTION_GATE_BLOCKED.json"
    assert sidecar.is_file()
    assert not run_root.exists()


def test_passed_wrapper_persists_gate_in_run_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    decision = {
        "schema_version": "all-auto-promotion-gate-v1",
        "status": "PASS",
        "target_stage": "hpo",
        "failures": [],
    }
    monkeypatch.setattr(gate, "evaluate_promotion_gate", lambda **_kwargs: decision)

    def runner(
        _project_root: Path,
        _config: CampaignConfig,
        run_root: Path,
        _stage: CampaignStage,
        *,
        source_run: Path | None,
        resume: bool,
    ) -> dict[str, Any]:
        assert source_run is None
        assert resume is False
        run_root.mkdir()
        manifest = {"status": "PASS", "stage": "hpo"}
        write_json(run_root / "manifest.json", manifest)
        write_sha256s(run_root)
        return manifest

    run_root = tmp_path / "hpo-run"
    result = gate.run_stage_with_promotion_gate(
        runner=runner,
        project_root=tmp_path,
        config=_config(tmp_path, gpu=False),
        run_root=run_root,
        target_stage=CampaignStage.HPO,
        source_run=None,
        coverage_run=tmp_path / "coverage",
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "PASS"
    assert result["promotion_gate_status"] == "PASS"
    assert result["promotion_gate_path"] == "PROMOTION_GATE.json"
    assert (run_root / "PROMOTION_GATE.json").is_file()
    assert (run_root / "SHA256SUMS").is_file()
