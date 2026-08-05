from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.autogluon_campaign.runtime_certification import (
    CertificationStatus,
    RuntimeCertificationConfig,
    default_scenarios,
    run_runtime_certification,
)


FAKE_PROVIDER = r'''
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
artifact = Path(request["artifact_dir"])
artifact.mkdir(parents=True, exist_ok=True)
for name in (
    "loto_provider_context_v2.json",
    "loto_execution_plan_v2.json",
    "loto_timeline_mapping_v2.json",
):
    (artifact / name).write_text("{}\n")
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
    "run_id": request["run_id"],
    "status": "OK",
    "operation": request["operation"],
    "predictions": predictions,
    "model_inventory": [],
    "ensemble_inventory": [],
    "argument_ledger": [],
    "artifacts": {
        "provider_context": str(artifact / "loto_provider_context_v2.json"),
        "execution_plan": str(artifact / "loto_execution_plan_v2.json"),
        "timeline_mapping": str(artifact / "loto_timeline_mapping_v2.json"),
    },
    "metadata": {
        "finite": True,
        "selected_model_ids": request["model_ids"],
    },
    "runtime_evidence": {
        "requested_device": request["requested_device"],
        "resolved_device": "cpu",
        "cuda_available": False,
        "gpu_used": False,
        "cpu_fallback": request["requested_device"] == "cuda",
        "pid": os.getpid(),
        "evidence_status": "PARTIAL",
    },
    "error": None,
}
args.response.parent.mkdir(parents=True, exist_ok=True)
args.response.write_text(json.dumps(response) + "\n")
'''


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
