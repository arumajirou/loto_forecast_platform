from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_gate import (
    EXPECTED_QUANTILE_KEYS,
    sha256_file,
    sha256_payload,
)

MODEL_REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
CONFIG_SHA = "6b74b03c8ec199fabc352c0203465958142ca468183da68549652734836f853d"
WEIGHT_SHA = "fb5652a3db8ea572606221b7cb1e77bb8962b168e4d4cc752cf31ceb04074669"
LOCK_SHA = "a" * 64
SOURCE_COMMIT = "b" * 40
SOURCE_TREE = "c" * 40


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prediction_identity(response: dict[str, Any]) -> str:
    return sha256_payload(
        {
            "point_forecast": response["point_forecast"],
            "quantiles": response["quantiles"],
            "series_identity": response["series_identity"],
            "prediction_index": response["prediction_index"],
        }
    )


def _response(
    *,
    runtime_lane: str,
    device: str,
    process_id: int,
    case_index: int,
) -> dict[str, Any]:
    quantiles = {
        key: [[case_index + quantile_index / 10, case_index + 1 + quantile_index / 10]]
        for quantile_index, key in enumerate(EXPECTED_QUANTILE_KEYS, start=1)
    }
    return {
        "status": "OK",
        "point_forecast": quantiles["q0.5"],
        "quantiles": quantiles,
        "series_identity": ["n1"],
        "prediction_index": [1, 2],
        "artifact_reference": {
            "model_revision": MODEL_REVISION,
            "config_sha256": CONFIG_SHA,
            "weight_sha256": WEIGHT_SHA,
        },
        "model_identity": {
            "model_id": "moirai-2.0-r-small",
            "revision": MODEL_REVISION,
        },
        "covariate_evidence": {
            "past_feature_names": [],
            "future_feature_names": [],
            "actuals_used": False,
        },
        "runtime_evidence": {
            "runtime_lane": runtime_lane,
            "requested_device": device,
            "execution_device": device,
            "cpu_fallback": False,
            "process_id": process_id,
            "model_parameter_device": device,
        },
        "gpu_evidence": {
            "provider_pid": process_id,
            "cpu_fallback": False,
            "gpu_pid": process_id if device == "cuda" else None,
            "peak_vram_bytes": 1024 if device == "cuda" else 0,
        },
        "effective_arguments": {
            "predictor_device": device,
            "forward_device_evidence": {
                "forward_call_count": 1,
                "input_tensor_devices": [device],
                "output_tensor_devices": [device],
            },
        },
    }


def _run_artifacts(
    *,
    run_dir: Path,
    request: dict[str, Any],
    response: dict[str, Any],
    device: str,
) -> dict[str, Any]:
    _write_json(run_dir / "request.json", request)
    _write_json(run_dir / "response.json", response)
    (run_dir / "stdout.log").write_text("provider ok\n", encoding="utf-8")
    (run_dir / "stderr.log").write_text("", encoding="utf-8")
    (run_dir / "exit_code.txt").write_text("0\n", encoding="utf-8")
    process_id = response["runtime_evidence"]["process_id"]
    if device == "cuda":
        monitor = {
            "before": {
                "memory": [{"gpu_uuid": "GPU-test", "used_memory_mib": 100}],
                "processes": [],
                "errors": [],
            },
            "samples": [
                {
                    "memory": [{"gpu_uuid": "GPU-test", "used_memory_mib": 612}],
                    "processes": [
                        {
                            "pid": process_id,
                            "gpu_uuid": "GPU-test",
                            "used_memory_mib": 512,
                        }
                    ],
                    "errors": [],
                }
            ],
            "after": {
                "memory": [{"gpu_uuid": "GPU-test", "used_memory_mib": 100}],
                "processes": [],
                "errors": [],
            },
        }
    else:
        monitor = {
            "before": {"memory": [], "processes": [], "errors": []},
            "samples": [{"memory": [], "processes": [], "errors": []}],
            "after": {"memory": [], "processes": [], "errors": []},
        }
    _write_json(run_dir / "gpu_monitor.json", monitor)
    external = {
        "requested_device": device,
        "provider_pid": process_id,
        "gpu_uuid": "GPU-test" if device == "cuda" else None,
        "external_pid_match": device == "cuda",
        "peak_process_memory_mib": 512 if device == "cuda" else 0,
        "pid_absent_after_exit": True,
        "vram_before_mib": 100 if device == "cuda" else None,
        "vram_after_mib": 100 if device == "cuda" else None,
    }
    evidence = {
        "label": run_dir.name,
        "command": ["uv", "run"],
        "process_id": process_id,
        "request_sha256": sha256_file(run_dir / "request.json"),
        "response_sha256": sha256_file(run_dir / "response.json"),
        "stdout_sha256": sha256_file(run_dir / "stdout.log"),
        "stderr_sha256": sha256_file(run_dir / "stderr.log"),
        "external_gpu": external,
        "response": response,
    }
    _write_json(run_dir / "run_evidence.json", evidence)
    return evidence
