from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from loto.autogluon_campaign.runtime_certification import (
    CertificationStatus,
    RuntimeCertificationConfig,
    default_scenarios,
    run_runtime_certification,
)

FAKE_PROVIDER = r"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--request", type=Path, required=True)
parser.add_argument("--response", type=Path, required=True)
args = parser.parse_args()
request = json.loads(args.request.read_text())
failed_scenario = os.environ.get("FAKE_FAIL_SCENARIO")
if failed_scenario and request["run_id"].endswith(failed_scenario):
    raise SystemExit(7)
artifact = Path(request["artifact_dir"])
artifact.mkdir(parents=True, exist_ok=True)
artifact_output = artifact
if os.environ.get("FAKE_ARTIFACT_ESCAPE") == "1":
    artifact_output = artifact.parent / "escaped-artifacts"
    artifact_output.mkdir(parents=True, exist_ok=True)
for name in (
    "loto_provider_context_v2.json",
    "loto_execution_plan_v2.json",
    "loto_timeline_mapping_v2.json",
):
    (artifact_output / name).write_text("{}\n")
now = datetime.now(timezone.utc).isoformat()
predictions = []
for index in range(1, 4):
    predictions.append({
        "item_id": f"position-{index}",
        "timestamp": now,
        "horizon_step": 1,
        "mean": float(index),
        "quantiles": {"0.1": float(index), "0.5": float(index), "0.9": float(index)},
    })
response = {
    "schema_version": 2,
    "provider_version": 2,
    "run_id": os.environ.get("FAKE_RUN_ID", request["run_id"]),
    "status": "OK",
    "operation": os.environ.get("FAKE_OPERATION", request["operation"]),
    "predictions": predictions,
    "model_inventory": [],
    "ensemble_inventory": [],
    "argument_ledger": [],
    "artifacts": {
        "provider_context": str(artifact_output / "loto_provider_context_v2.json"),
        "execution_plan": str(artifact_output / "loto_execution_plan_v2.json"),
        "timeline_mapping": str(artifact_output / "loto_timeline_mapping_v2.json"),
    },
    "metadata": {
        "finite": True,
        "selected_model_ids": request["model_ids"],
    },
    "runtime_evidence": {
        "requested_device": request["requested_device"],
        "resolved_device": os.environ.get("FAKE_RESOLVED_DEVICE", "cpu"),
        "cuda_available": False,
        "gpu_used": os.environ.get("FAKE_GPU_USED") == "1",
        "cpu_fallback": request["requested_device"] == "cuda",
        "pid": os.getpid(),
        "evidence_status": "PARTIAL",
    },
    "error": None,
}
args.response.parent.mkdir(parents=True, exist_ok=True)
args.response.write_text(json.dumps(response) + "\n")
"""


def _fake_provider(tmp_path: Path) -> Path:
    path = tmp_path / "fake_provider.py"
    path.write_text(FAKE_PROVIDER, encoding="utf-8")
    return path


def test_default_campaign_contains_all_required_runtime_cases() -> None:
    scenario_ids = {scenario.scenario_id for scenario in default_scenarios()}
    assert scenario_ids == {
        "explicit-naive-fit",
        "explicit-naive-load",
        "explicit-theta-fit",
        "preset-fast-training",
        "multi-naive-theta",
        "hpo-seasonal-naive",
        "forced-cpu-fallback",
    }


def test_fake_runtime_certifies_all_scenarios_and_writes_hashes(tmp_path) -> None:
    provider = _fake_provider(tmp_path)
    output = tmp_path / "output"
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=output,
            provider_command=(sys.executable, str(provider)),
            timeout_seconds=10,
        )
    )
    assert report.status is CertificationStatus.VERIFIED
    assert report.verified_count == 7
    assert report.failed_count == 0
    assert len(report.report_sha256) == 64
    assert (output / "RUNTIME_CERTIFICATION_REPORT.json").is_file()
    assert (output / "SHA256SUMS").is_file()
    payload = json.loads((output / "RUNTIME_CERTIFICATION_REPORT.json").read_text())
    assert payload["report_sha256"] == report.report_sha256
    fallback = next(
        item for item in payload["scenarios"] if item["scenario_id"] == "forced-cpu-fallback"
    )
    assert fallback["runtime_evidence"]["cpu_fallback"] is True


def test_missing_provider_command_is_classified_as_blocked(tmp_path) -> None:
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "blocked",
            provider_command=(str(tmp_path / "does-not-exist"),),
            timeout_seconds=1,
            scenario_ids=("explicit-naive-fit",),
        )
    )
    assert report.status is CertificationStatus.BLOCKED_RUNTIME
    assert report.blocked_count == 1
    assert report.scenarios[0].return_code is None


def test_nonempty_output_directory_is_rejected_before_execution(tmp_path) -> None:
    provider = _fake_provider(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "stale-response.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="absent or empty"):
        run_runtime_certification(
            RuntimeCertificationConfig(
                repo_root=tmp_path,
                output_dir=output,
                provider_command=(sys.executable, str(provider)),
                timeout_seconds=10,
                scenario_ids=("explicit-naive-fit",),
            )
        )


def test_response_run_id_mismatch_fails_closed(tmp_path, monkeypatch) -> None:
    provider = _fake_provider(tmp_path)
    monkeypatch.setenv("FAKE_RUN_ID", "wrong-run")
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "run-id-mismatch",
            provider_command=(sys.executable, str(provider)),
            timeout_seconds=10,
            scenario_ids=("explicit-naive-fit",),
        )
    )
    assert report.status is CertificationStatus.FAILED
    assert any("run_id mismatch" in error for error in report.scenarios[0].errors)


def test_response_operation_mismatch_fails_closed(tmp_path, monkeypatch) -> None:
    provider = _fake_provider(tmp_path)
    monkeypatch.setenv("FAKE_OPERATION", "load_predict")
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "operation-mismatch",
            provider_command=(sys.executable, str(provider)),
            timeout_seconds=10,
            scenario_ids=("explicit-naive-fit",),
        )
    )
    assert report.status is CertificationStatus.FAILED
    assert any("operation mismatch" in error for error in report.scenarios[0].errors)


def test_artifact_paths_must_remain_inside_scenario_artifact_dir(tmp_path, monkeypatch) -> None:
    provider = _fake_provider(tmp_path)
    monkeypatch.setenv("FAKE_ARTIFACT_ESCAPE", "1")
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "escaped-artifact",
            provider_command=(sys.executable, str(provider)),
            timeout_seconds=10,
            scenario_ids=("explicit-naive-fit",),
        )
    )
    assert report.status is CertificationStatus.FAILED
    assert any("escapes artifact_dir" in error for error in report.scenarios[0].errors)


def test_load_scenario_is_blocked_when_fit_dependency_fails(tmp_path, monkeypatch) -> None:
    provider = _fake_provider(tmp_path)
    monkeypatch.setenv("FAKE_FAIL_SCENARIO", "explicit-naive-fit")
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "dependency-failure",
            provider_command=(sys.executable, str(provider)),
            timeout_seconds=10,
            scenario_ids=("explicit-naive-fit", "explicit-naive-load"),
        )
    )
    by_id = {item.scenario_id: item for item in report.scenarios}
    assert by_id["explicit-naive-fit"].status == CertificationStatus.FAILED.value
    assert by_id["explicit-naive-load"].status == CertificationStatus.BLOCKED_RUNTIME.value
    assert by_id["explicit-naive-load"].return_code is None
    assert "dependency not verified" in by_id["explicit-naive-load"].errors[0]


def test_cpu_scenario_rejects_gpu_runtime_evidence(tmp_path, monkeypatch) -> None:
    provider = _fake_provider(tmp_path)
    monkeypatch.setenv("FAKE_RESOLVED_DEVICE", "cuda")
    monkeypatch.setenv("FAKE_GPU_USED", "1")
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "cpu-evidence-mismatch",
            provider_command=(sys.executable, str(provider)),
            timeout_seconds=10,
            scenario_ids=("explicit-naive-fit",),
        )
    )
    assert report.status is CertificationStatus.FAILED
    assert any("did not resolve to CPU" in error for error in report.scenarios[0].errors)
    assert any("must not report GPU use" in error for error in report.scenarios[0].errors)
