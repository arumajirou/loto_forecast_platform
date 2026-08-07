from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_gate import (
    FORMAL_CASE_NAMES,
    sha256_file,
    sha256_payload,
    write_sha256_manifest,
)
from tests.moirai2_campaign.p8c_evidence_fixtures_core import (
    CONFIG_SHA,
    LOCK_SHA,
    MODEL_REVISION,
    SOURCE_COMMIT,
    SOURCE_TREE,
    WEIGHT_SHA,
    _prediction_identity,
    _response,
    _run_artifacts,
    _write_json,
)

def _case(
    *,
    root: Path,
    campaign_id: str,
    runtime_lane: str,
    device: str,
    case_name: str,
    case_index: int,
) -> dict[str, Any]:
    request = {
        "run_id": f"{campaign_id}.{case_name}",
        "model_id": "moirai-2.0-r-small",
        "repo_id": "Salesforce/moirai-2.0-R-small",
        "revision": MODEL_REVISION,
        "snapshot_path": "/snapshot",
        "seed": 1,
        "device": device,
        "local_files_only": True,
    }
    request_path = root / "requests" / f"{case_name}.json"
    _write_json(request_path, request)
    case_dir = root / "cases" / case_name
    response_a = _response(
        runtime_lane=runtime_lane,
        device=device,
        process_id=10_000 + (case_index * 2),
        case_index=case_index,
    )
    response_b = _response(
        runtime_lane=runtime_lane,
        device=device,
        process_id=10_001 + (case_index * 2),
        case_index=case_index,
    )
    evidence_a = _run_artifacts(
        run_dir=case_dir / "run-a",
        request=request,
        response=response_a,
        device=device,
    )
    evidence_b = _run_artifacts(
        run_dir=case_dir / "run-b",
        request=request,
        response=response_b,
        device=device,
    )
    prediction_sha = _prediction_identity(response_a)
    comparison = {
        "process_a": response_a["runtime_evidence"]["process_id"],
        "process_b": response_b["runtime_evidence"]["process_id"],
        "distinct_processes": True,
        "prediction_sha256_a": prediction_sha,
        "prediction_sha256_b": prediction_sha,
        "exact_prediction_match": True,
        "maximum_absolute_difference": 0.0,
        "artifact_identity_match": True,
        "model_identity_match": True,
        "covariate_identity_match": True,
    }
    certification = {
        "status": "PASS",
        "phase": "P8_RUNTIME_CERTIFICATION",
        "run_id": request["run_id"],
        "runtime_lane": runtime_lane,
        "requested_device": device,
        "request_sha256": sha256_payload(request),
        "separate_process_reload": True,
        "save_load_status": "BASE_SNAPSHOT_RELOADED",
        "prediction_comparison": comparison,
        "run_a": {key: value for key, value in evidence_a.items() if key != "response"},
        "run_b": {key: value for key, value in evidence_b.items() if key != "response"},
    }
    _write_json(case_dir / "certification.json", certification)
    (case_dir / "campaign_launcher.stdout.log").write_text("ok\n", encoding="utf-8")
    (case_dir / "campaign_launcher.stderr.log").write_text("", encoding="utf-8")
    (case_dir / "campaign_launcher.exit_code.txt").write_text("0\n", encoding="utf-8")
    result = {
        "case": case_name,
        "status": "PASS",
        "message": "two-process certification passed",
        "request_path": f"requests/{case_name}.json",
        "request_sha256": sha256_file(request_path),
        "certification_path": f"cases/{case_name}/certification.json",
        "launcher_return_code": 0,
        "launcher_timed_out": False,
        "certification": certification,
    }
    _write_json(case_dir / "campaign_case_result.json", result)
    return result


def _campaign(
    root: Path,
    *,
    campaign_id: str,
    runtime_lane: str,
    device: str,
    source_commit: str = SOURCE_COMMIT,
) -> Path:
    root.mkdir(parents=True)
    source_identity = {
        "schema_version": "moirai2-source-identity-v1",
        "repo_root": "/repo",
        "commit_sha": source_commit,
        "tree_sha": SOURCE_TREE,
        "worktree_clean": True,
        "changed_paths": [],
        "principal_file_sha256": {"scripts/run_moirai2_provider.py": "d" * 64},
    }
    config = {
        "schema_version": "moirai2-p8-runtime-campaign-v1",
        "campaign_id": campaign_id,
        "runtime_lane": runtime_lane,
        "device": device,
        "snapshot_path": "/snapshot",
        "selected_cases": list(FORMAL_CASE_NAMES),
        "formal_entrypoint": "scripts/run_moirai2_runtime_campaign_p8c.py",
        "execution_policy": "strictly_serial",
        "parallel_case_count": 1,
        "history_length": 128,
        "context_length": 128,
        "prediction_length": 1,
        "timeout_seconds": 1800,
        "monitor_interval_seconds": 0.25,
        "prepare_only": False,
        "seed": 1,
        "source_identity": source_identity,
    }
    _write_json(root / "campaign_config.json", config)
    preflight = {
        "status": "PASS",
        "phase": "P8_RUNTIME_PREFLIGHT",
        "runtime_lane": runtime_lane,
        "requested_device": device,
        "lane_evidence": {
            "lock_review": {
                "runtime_lane": runtime_lane,
                "lock_sha256": LOCK_SHA,
                "reviewer": "operator",
                "reviewed_at": "2026-08-06T07:00:00+09:00",
            },
            "snapshot_files": {
                "config.json": CONFIG_SHA,
                "model.safetensors": WEIGHT_SHA,
            },
        },
        "probe": {"torch_cuda_available": device == "cuda"},
    }
    _write_json(root / "preflight.json", preflight)
    case_results = [
        _case(
            root=root,
            campaign_id=campaign_id,
            runtime_lane=runtime_lane,
            device=device,
            case_name=case_name,
            case_index=index,
        )
        for index, case_name in enumerate(FORMAL_CASE_NAMES)
    ]
    summary = {
        "schema_version": "moirai2-p8-runtime-campaign-v1",
        "status": "PASS",
        "phase": "P8_RUNTIME_CAMPAIGN",
        "runtime_lane": runtime_lane,
        "requested_device": device,
        "required_cases": list(FORMAL_CASE_NAMES),
        "observed_cases": list(FORMAL_CASE_NAMES),
        "passed_case_count": 6,
        "required_case_count": 6,
        "failures": [],
        "case_result_sha256": sha256_payload(case_results),
        "formal_runtime_certified": True,
        "accuracy_claimed": False,
        "oof_opened": False,
        "holdout_opened": False,
        "prospective_opened": False,
        "campaign_id": campaign_id,
        "preflight_status": "PASS",
    }
    _write_json(root / "campaign_summary.json", summary)
    (root / "p8c_campaign.stdout.log").write_text("campaign ok\n", encoding="utf-8")
    (root / "p8c_campaign.stderr.log").write_text("", encoding="utf-8")
    (root / "p8c_campaign.exit_code.txt").write_text("0\n", encoding="utf-8")
    _write_json(
        root / "P8C_LAUNCH_EVIDENCE.json",
        {
            "schema_version": "moirai2-p8c-launch-evidence-v1",
            "formal_entrypoint": "scripts/run_moirai2_runtime_campaign_p8c.py",
            "command": ["python", "scripts/run_moirai2_runtime_campaign.py"],
            "return_code": 0,
            "started_at_unix_ns": 1,
            "ended_at_unix_ns": 2,
            "duration_seconds": 1e-9,
            "source_identity": source_identity,
            "stdout_sha256": sha256_file(root / "p8c_campaign.stdout.log"),
            "stderr_sha256": sha256_file(root / "p8c_campaign.stderr.log"),
            "exit_code_sha256": sha256_file(root / "p8c_campaign.exit_code.txt"),
            "campaign_config_sha256": sha256_file(root / "campaign_config.json"),
        },
    )
    files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    _write_json(
        root / "ARTIFACT_MANIFEST.json",
        {
            "schema_version": "moirai2-p8-runtime-campaign-artifacts-v1",
            "files": files,
            "file_count": len(files),
        },
    )
    write_sha256_manifest(root, root / "SHA256SUMS")
    return root


