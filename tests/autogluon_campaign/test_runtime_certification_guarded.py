from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.autogluon_campaign.runtime_certification import RuntimeCertificationConfig
from loto.autogluon_campaign.runtime_certification_guarded import (
    CertificationStatus,
    finalize_guarded_output,
    run_guarded_certification,
    verify_guarded_output,
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
failed = os.environ.get("FAKE_FAIL_SCENARIO")
if failed and request["run_id"].endswith(failed):
    raise SystemExit(7)
artifact = Path(request["artifact_dir"])
artifact.mkdir(parents=True, exist_ok=True)
for name in (
    "loto_provider_context_v2.json",
    "loto_execution_plan_v2.json",
    "loto_timeline_mapping_v2.json",
):
    (artifact / name).write_text("{}\n")
now = datetime.now(timezone.utc).isoformat()
predictions = [
    {
        "item_id": f"position-{index}",
        "timestamp": now,
        "horizon_step": 1,
        "mean": float(index),
        "quantiles": {"0.1": float(index), "0.5": float(index), "0.9": float(index)},
    }
    for index in range(1, 4)
]
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
    "metadata": {"finite": True, "selected_model_ids": request["model_ids"]},
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


def _provider(tmp_path: Path) -> Path:
    path = tmp_path / "fake_provider.py"
    path.write_text(FAKE_PROVIDER, encoding="utf-8")
    return path


def _config(tmp_path: Path, output: Path, scenarios: tuple[str, ...]) -> RuntimeCertificationConfig:
    return RuntimeCertificationConfig(
        repo_root=tmp_path,
        output_dir=output,
        provider_command=(sys.executable, str(_provider(tmp_path))),
        timeout_seconds=10,
        scenario_ids=scenarios,
    )


def test_guarded_output_passes_independent_verification(tmp_path) -> None:
    output = tmp_path / "pass"
    payload = run_guarded_certification(
        _config(tmp_path, output, ("explicit-naive-fit",))
    )
    assert payload["status"] == CertificationStatus.VERIFIED.value
    assert payload["p11_guard_schema_version"] == 1
    assert verify_guarded_output(output) == ()


def test_unexpected_failure_overrides_partial_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_FAIL_SCENARIO", "explicit-theta-fit")
    output = tmp_path / "mixed"
    payload = run_guarded_certification(
        _config(
            tmp_path,
            output,
            ("explicit-naive-fit", "explicit-theta-fit"),
        )
    )
    assert payload["verified_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["status"] == CertificationStatus.FAILED.value


def test_tampering_is_detected(tmp_path) -> None:
    output = tmp_path / "tamper"
    run_guarded_certification(_config(tmp_path, output, ("explicit-naive-fit",)))
    request = output / "scenarios" / "explicit-naive-fit" / "request.json"
    request.write_text("{}\n", encoding="utf-8")
    assert any("SHA-256 mismatch" in error for error in verify_guarded_output(output))


def test_symlink_is_recorded_as_failed_and_excluded_from_manifest(tmp_path) -> None:
    output = tmp_path / "symlink"
    run_guarded_certification(_config(tmp_path, output, ("explicit-naive-fit",)))
    link = output / "model-artifacts" / "naive" / "outside-link"
    link.symlink_to(Path(__file__))
    payload = finalize_guarded_output(output)
    assert payload["status"] == CertificationStatus.FAILED.value
    assert any("symbolic link" in error for error in payload["p11_evidence_errors"])
    assert "outside-link" not in (output / "SHA256SUMS").read_text(encoding="utf-8")


def test_verification_id_is_present_and_report_hash_is_current(tmp_path) -> None:
    output = tmp_path / "identity"
    payload = run_guarded_certification(_config(tmp_path, output, ("explicit-naive-fit",)))
    disk = json.loads((output / "RUNTIME_CERTIFICATION_REPORT.json").read_text())
    assert disk["p11_verification_id"] == payload["p11_verification_id"]
    assert len(disk["report_sha256"]) == 64
