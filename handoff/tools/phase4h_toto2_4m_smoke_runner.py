#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(os.environ.get("LOTO_ROOT", "/mnt/e/env/ts/loto_forecast_platform"))
SOURCE_WT = Path(
    os.environ.get(
        "LOTO_SOURCE_WT",
        "/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248",
    )
)
HANDOFF_WT = Path(
    os.environ.get(
        "LOTO_HANDOFF_WT",
        "/mnt/e/env/ts/worktrees/loto-runtime-handoff",
    )
)
HANDOFF = HANDOFF_WT / "handoff"
BRANCH = "ops/runtime-audit-handoff"
EXPECTED_SOURCE_SHA = "8af95b2be18280589cbbb13aa1fc32dfb793767c"
ENV_NAME = "environments/toto2-4m-py312"
RUNTIME = ROOT / ".runtime-envs/toto/bin/python"
ENV_PROJECT = SOURCE_WT / ENV_NAME
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase4h-toto2-4m-smoke-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase4h"
REQUEST_PATH = LOCAL_OUT / "request.json"
RESPONSE_PATH = LOCAL_OUT / "response.json"
CERT_RUN_DIR = LOCAL_OUT / "runtime-certification"

EXPECTED_PYTHON_PREFIX = "3.12."
EXPECTED_TORCH_PREFIX = "2.13.0"
EXPECTED_TORCH_CUDA = "13.0"
EXPECTED_TOTO_2 = "2.0.0"
EXPECTED_TOTO_MODELS = "1.0.0"
EXPECTED_MODEL_ID = "toto-2.0-4m"
EXPECTED_REPO_ID = "Datadog/Toto-2.0-4m"
EXPECTED_MODEL_REVISION = "8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9"
EXPECTED_SOURCE_REVISION = "44ea4e88852228039564aa3e76fac26aafac0803"
EXPECTED_MODEL_CLASS = "Toto2Model"
EXPECTED_MODEL_PARAMETER_COUNT = 4_144_448
EXPECTED_MODEL_LICENSE = "Apache-2.0"
EXPECTED_MODEL_SHA256 = "316660d5afb47943e531f39242e0b02ca0b8bb73be5709dfe07ca80dfce9805e"
EXPECTED_MODEL_SIZE = 16_582_848


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def git_output(args: list[str]) -> str:
    proc = run(["git", "-C", str(HANDOFF_WT), *args], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def source_gate() -> None:
    head = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"])
    if head.returncode != 0 or head.stdout.strip() != EXPECTED_SOURCE_SHA:
        raise RuntimeError(
            f"SOURCE_SHA_GATE_FAILED:expected={EXPECTED_SOURCE_SHA}:actual={head.stdout.strip()}"
        )
    status = run(["git", "-C", str(SOURCE_WT), "status", "--porcelain"])
    if status.returncode != 0 or status.stdout.strip():
        raise RuntimeError("SOURCE_WORKTREE_DIRTY")


def handoff_sync() -> None:
    if git_output(["branch", "--show-current"]) != BRANCH:
        raise RuntimeError("HANDOFF_BRANCH_GATE_FAILED")
    if git_output(["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_WORKTREE_DIRTY")
    git_output(["fetch", "--prune", "origin"])
    proc = run(
        ["git", "-C", str(HANDOFF_WT), "pull", "--ff-only", "origin", BRANCH],
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"HANDOFF_PULL_FAILED:{proc.stderr.strip()}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def prerequisite_gate() -> dict[str, str]:
    phase4g_path = HANDOFF / "phase4g/summary.json"
    if not phase4g_path.exists():
        raise RuntimeError("PHASE4G_SUMMARY_MISSING")
    phase4g = json.loads(phase4g_path.read_text("utf-8"))
    if phase4g.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4G_NOT_VERIFIED")

    phase3d = json.loads((HANDOFF / "phase3d/summary.json").read_text("utf-8"))
    if phase3d.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError("PHASE3D_SOURCE_SHA_MISMATCH")
    ready = read_tsv(HANDOFF / "phase3d/phase4-ready-queue.tsv")
    row = next((item for item in ready if item.get("environment") == ENV_NAME), None)
    if row is None:
        raise RuntimeError("TOTO2_4M_NOT_IN_PHASE4_READY_QUEUE")
    if row.get("phase4_smoke_allowed") != "True":
        raise RuntimeError("TOTO2_4M_PHASE4_SMOKE_NOT_ALLOWED")
    if row.get("lane") != "REUSABLE_COMPATIBLE_VENV":
        raise RuntimeError(f"TOTO2_4M_UNEXPECTED_LANE:{row.get('lane')}")
    expected_runtime = str(ROOT / ".runtime-envs/toto")
    if row.get("candidate_runtime") != expected_runtime:
        raise RuntimeError(
            "TOTO2_4M_RUNTIME_IDENTITY_MISMATCH:"
            f"expected={expected_runtime}:actual={row.get('candidate_runtime')}"
        )
    if row.get("candidate_probe_status") != "PASS":
        raise RuntimeError("TOTO2_4M_CANDIDATE_PROBE_NOT_PASS")
    return row


def offline_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(SOURCE_WT / "src"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "CUDA_VISIBLE_DEVICES": "0",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    return env


def runtime_probe() -> dict[str, Any]:
    if not RUNTIME.exists() or not os.access(RUNTIME, os.X_OK):
        raise RuntimeError(f"TOTO2_RUNTIME_MISSING:{RUNTIME}")
    code = r'''
import importlib.metadata
import json
import platform
import sys
import torch
from loto.toto2_campaign.model_manifest import (
    MODEL_ID, REPO_ID, MODEL_REVISION, SOURCE_REVISION, MODEL_CLASS,
    MODEL_PARAMETER_COUNT, MODEL_LICENSE, TOTO_2_VERSION, TOTO_MODELS_VERSION,
    CERTIFIED_PYTHON_SERIES, CERTIFIED_TORCH_VERSION_PREFIX, CERTIFIED_CUDA_VERSION,
    ARTIFACT_SHA256, ARTIFACT_SIZE_BYTES,
)
from toto2 import Toto2Model
payload = {
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "torch": str(torch.__version__),
    "torch_cuda": str(torch.version.cuda) if torch.version.cuda else None,
    "torch_cuda_available": bool(torch.cuda.is_available()),
    "torch_cuda_device_count": int(torch.cuda.device_count()),
    "torch_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "toto_2": importlib.metadata.version("toto-2"),
    "toto_models": importlib.metadata.version("toto-models"),
    "toto2_model_import_class": Toto2Model.__name__,
    "model_id": MODEL_ID,
    "repo_id": REPO_ID,
    "model_revision": MODEL_REVISION,
    "source_revision": SOURCE_REVISION,
    "model_class": MODEL_CLASS,
    "model_parameter_count": MODEL_PARAMETER_COUNT,
    "model_license": MODEL_LICENSE,
    "manifest_toto_2_version": TOTO_2_VERSION,
    "manifest_toto_models_version": TOTO_MODELS_VERSION,
    "certified_python_series": CERTIFIED_PYTHON_SERIES,
    "certified_torch_prefix": CERTIFIED_TORCH_VERSION_PREFIX,
    "certified_cuda": CERTIFIED_CUDA_VERSION,
    "artifact_sha256": ARTIFACT_SHA256,
    "artifact_size_bytes": ARTIFACT_SIZE_BYTES,
}
print(json.dumps(payload, sort_keys=True))
'''
    proc = run([str(RUNTIME), "-I", "-c", code], timeout=120, env=offline_env())
    (LOCAL_OUT / "runtime-probe.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "runtime-probe.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"TOTO2_RUNTIME_PROBE_FAILED:{proc.stderr.strip()}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    checks = {
        "python": str(payload.get("python", "")).startswith(EXPECTED_PYTHON_PREFIX),
        "prefix": payload.get("prefix") == str(ROOT / ".runtime-envs/toto"),
        "torch": str(payload.get("torch", "")).startswith(EXPECTED_TORCH_PREFIX),
        "torch_cuda": payload.get("torch_cuda") == EXPECTED_TORCH_CUDA,
        "cuda_available": payload.get("torch_cuda_available") is True,
        "cuda_device_count": int(payload.get("torch_cuda_device_count", 0)) >= 1,
        "toto_2": payload.get("toto_2") == EXPECTED_TOTO_2,
        "toto_models": payload.get("toto_models") == EXPECTED_TOTO_MODELS,
        "model_import": payload.get("toto2_model_import_class") == EXPECTED_MODEL_CLASS,
        "model_id": payload.get("model_id") == EXPECTED_MODEL_ID,
        "repo_id": payload.get("repo_id") == EXPECTED_REPO_ID,
        "model_revision": payload.get("model_revision") == EXPECTED_MODEL_REVISION,
        "source_revision": payload.get("source_revision") == EXPECTED_SOURCE_REVISION,
        "model_class": payload.get("model_class") == EXPECTED_MODEL_CLASS,
        "model_parameter_count": payload.get("model_parameter_count") == EXPECTED_MODEL_PARAMETER_COUNT,
        "model_license": payload.get("model_license") == EXPECTED_MODEL_LICENSE,
        "model_weight_sha": (payload.get("artifact_sha256") or {}).get("model.safetensors") == EXPECTED_MODEL_SHA256,
        "model_weight_size": (payload.get("artifact_size_bytes") or {}).get("model.safetensors") == EXPECTED_MODEL_SIZE,
    }
    failed = [key for key, value in checks.items() if value is not True]
    if failed:
        raise RuntimeError(f"TOTO2_RUNTIME_PROBE_CONTRACT_FAILED:{failed}:payload={payload}")
    payload["checks"] = checks
    return payload


def environment_contract() -> dict[str, Any]:
    pyproject = ENV_PROJECT / "pyproject.toml"
    if not pyproject.exists():
        raise RuntimeError(f"TOTO2_PYPROJECT_MISSING:{pyproject}")
    text = pyproject.read_text("utf-8")
    required = (
        'requires-python = ">=3.12,<3.13"',
        '"numpy>=2.0,<3"',
        '"pydantic>=2.10,<3"',
        '"toto-models==1.0.0"',
        '"toto-2==2.0.0"',
        '"torch==2.13.0"',
    )
    if not all(token in text for token in required):
        raise RuntimeError("TOTO2_PYPROJECT_CONTRACT_MISMATCH")
    lock = ENV_PROJECT / "uv.lock"
    return {
        "pyproject_path": str(pyproject),
        "pyproject_sha256": sha256_file(pyproject),
        "source_uv_lock_exists": lock.exists(),
        "source_uv_lock_sha256": sha256_file(lock) if lock.exists() else None,
        "selected_runtime": str(ROOT / ".runtime-envs/toto"),
        "dependencies_modified": False,
        "lockfile_modified": False,
        "existing_compatible_venv_reused": True,
    }


def gpu_inventory() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,uuid,memory.total,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ]
    proc = run(command, timeout=20)
    if proc.returncode != 0:
        raise RuntimeError(f"NVIDIA_SMI_GPU_INVENTORY_FAILED:{proc.stderr.strip()}")
    rows = []
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 6:
            raise RuntimeError(f"NVIDIA_SMI_GPU_ROW_INVALID:{line}")
        rows.append(
            {
                "index": int(parts[0]),
                "name": parts[1],
                "uuid": parts[2],
                "memory_total_mib": int(parts[3]),
                "memory_free_mib": int(parts[4]),
                "driver_version": parts[5],
            }
        )
    if not rows:
        raise RuntimeError("NVIDIA_SMI_NO_GPU")
    return {"command": command, "rows": rows}


def snapshot_candidates() -> list[Path]:
    revision = EXPECTED_MODEL_REVISION
    slug = "models--Datadog--Toto-2.0-4m"
    candidates: list[Path] = []
    override = os.environ.get("TOTO2_4M_SNAPSHOT")
    if override:
        candidates.append(Path(override).expanduser())

    hub_cache = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if hub_cache:
        candidates.append(Path(hub_cache).expanduser() / slug / "snapshots" / revision)
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        candidates.append(Path(hf_home).expanduser() / "hub" / slug / "snapshots" / revision)

    candidates.extend(
        [
            Path.home() / ".cache/huggingface/hub" / slug / "snapshots" / revision,
            Path("/mnt/e/env/hf_models") / slug / "snapshots" / revision,
            Path("/mnt/e/env/hf_models/.cache/huggingface/hub") / slug / "snapshots" / revision,
            Path("/mnt/e/env/hf_models/Datadog/Toto-2.0-4m") / revision,
            Path("/mnt/e/env/hf_models/Toto-2.0-4m") / revision,
            ROOT / ".cache/huggingface/hub" / slug / "snapshots" / revision,
        ]
    )

    search_roots = [
        Path.home() / ".cache/huggingface",
        Path("/mnt/e/env/hf_models"),
        ROOT / ".cache",
        ROOT / ".runtime-cache",
    ]
    for root in search_roots:
        if not root.is_dir():
            continue
        proc = run(
            [
                "find",
                str(root),
                "-maxdepth",
                "8",
                "-type",
                "d",
                "-name",
                revision,
                "-print",
            ],
            timeout=30,
        )
        if proc.returncode == 0:
            candidates.extend(Path(line.strip()) for line in proc.stdout.splitlines() if line.strip())

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def verify_snapshot_candidate(candidate: Path) -> tuple[bool, dict[str, Any] | str]:
    if not candidate.is_dir():
        return False, "not-a-directory"
    code = r'''
import json
import sys
from pathlib import Path
from loto.toto2_campaign.runtime_executor import verify_snapshot
try:
    print(json.dumps(verify_snapshot(Path(sys.argv[1])), sort_keys=True))
except Exception as exc:
    print(json.dumps({"error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True))
    raise SystemExit(2)
'''
    proc = run(
        [str(RUNTIME), "-I", "-c", code, str(candidate)],
        timeout=180,
        env=offline_env(),
    )
    if proc.returncode != 0:
        detail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr.strip()
        return False, detail
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    return True, payload


def resolve_snapshot() -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for candidate in snapshot_candidates():
        ok, detail = verify_snapshot_candidate(candidate)
        attempts.append({"path": str(candidate), "verified": ok, "detail": detail})
        if ok:
            payload = dict(detail) if isinstance(detail, dict) else {}
            return candidate.resolve(), payload, attempts
    dump_json(LOCAL_OUT / "snapshot-discovery.json", {"attempts": attempts})
    raise RuntimeError(
        "TOTO2_SNAPSHOT_NOT_FOUND_OR_INVALID:"
        f"revision={EXPECTED_MODEL_REVISION}:set TOTO2_4M_SNAPSHOT to the exact cached snapshot"
    )


def build_request(snapshot: Path, runtime: dict[str, Any]) -> dict[str, Any]:
    history = [{"n1": int(1 + (index % 20))} for index in range(128)]
    payload = {
        "schema_version": 2,
        "run_id": f"phase4h-{RUN_ID}",
        "operation": "predict",
        "model_id": runtime["model_id"],
        "repo_id": runtime["repo_id"],
        "revision": runtime["model_revision"],
        "source_revision": runtime["source_revision"],
        "model_license": runtime["model_license"],
        "game_geometry": {
            "game_id": "phase4h_synthetic",
            "position_count": 1,
            "candidate_min": 1,
            "candidate_max": 20,
            "strictly_increasing": False,
        },
        "series_layout": "position_univariate",
        "position_columns": ["n1"],
        "history": history,
        "timestamps": list(range(1, 129)),
        "time_semantics": "draw_sequence",
        "context_length": 128,
        "prediction_length": 1,
        "native_quantile_levels": [round(index / 10, 1) for index in range(1, 10)],
        "point_method": "median_q0.5",
        "batch_size": 1,
        "decode_block_size": 32,
        "device": "cuda",
        "dtype": "float32",
        "seed": 1,
        "local_files_only": True,
        "snapshot_path": str(snapshot),
    }
    dump_json(REQUEST_PATH, payload)
    return payload


def run_certification(snapshot: Path) -> dict[str, Any]:
    script = SOURCE_WT / "scripts/certify_toto2_4m_runtime.py"
    if not script.is_file():
        raise RuntimeError(f"TOTO2_CERTIFIER_MISSING:{script}")
    command = [
        str(RUNTIME),
        str(script),
        "--request",
        str(REQUEST_PATH),
        "--response",
        str(RESPONSE_PATH),
        "--snapshot",
        str(snapshot),
        "--isolated-python",
        str(RUNTIME),
        "--run-dir",
        str(CERT_RUN_DIR),
        "--ready-timeout-seconds",
        "180",
        "--gpu-capture-timeout-seconds",
        "60",
    ]
    proc = run(command, cwd=SOURCE_WT, timeout=600, env=offline_env())
    (LOCAL_OUT / "certification.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "certification.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if not RESPONSE_PATH.exists():
        raise RuntimeError(
            f"TOTO2_CERTIFICATION_RESPONSE_MISSING:rc={proc.returncode}:stderr={proc.stderr[-2000:]}"
        )
    response = json.loads(RESPONSE_PATH.read_text("utf-8"))
    if proc.returncode != 0:
        raise RuntimeError(
            f"TOTO2_CERTIFICATION_FAILED:rc={proc.returncode}:response={response}:stderr={proc.stderr[-2000:]}"
        )
    return response


def all_finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, list):
        return all(all_finite(item) for item in value)
    if isinstance(value, dict):
        return all(all_finite(item) for item in value.values())
    return False


def inspect_native_outputs() -> dict[str, Any]:
    first = CERT_RUN_DIR / "process-1/native_output.npy"
    second = CERT_RUN_DIR / "process-2/native_output.npy"
    if not first.is_file() or not second.is_file():
        raise RuntimeError("TOTO2_NATIVE_OUTPUT_MISSING")
    code = r'''
import hashlib
import json
import sys
import numpy as np

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
a = np.load(sys.argv[1], allow_pickle=False)
b = np.load(sys.argv[2], allow_pickle=False)
print(json.dumps({
    "first_shape": list(a.shape),
    "second_shape": list(b.shape),
    "first_finite": bool(np.isfinite(a).all()),
    "second_finite": bool(np.isfinite(b).all()),
    "exact_equal": bool(np.array_equal(a, b)),
    "first_sha256": sha(sys.argv[1]),
    "second_sha256": sha(sys.argv[2]),
    "dtype": str(a.dtype),
}, sort_keys=True))
'''
    proc = run([str(RUNTIME), "-I", "-c", code, str(first), str(second)], timeout=60, env=offline_env())
    if proc.returncode != 0:
        raise RuntimeError(f"TOTO2_NATIVE_OUTPUT_INSPECTION_FAILED:{proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def validate_response(response: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(response.get("runtime_evidence") or {})
    artifact = dict(response.get("artifact_reference") or {})
    replay = dict(artifact.get("replay") or {})
    processes = list(artifact.get("processes") or [])
    snapshot = dict(artifact.get("snapshot") or {})
    model_identity = dict(response.get("model_identity") or {})
    effective = dict(response.get("effective_arguments") or {})

    process_gpu_ok = len(processes) == 2 and all(
        bool((item.get("gpu_evidence") or {}).get("captured"))
        and int((item.get("gpu_evidence") or {}).get("max_gpu_memory_mib", 0)) > 0
        and bool((item.get("runtime_evidence") or {}).get("external_gpu_pid_captured"))
        and int((item.get("runtime_evidence") or {}).get("peak_vram_bytes", 0)) > 0
        and not bool((item.get("runtime_evidence") or {}).get("cpu_fallback"))
        and str((item.get("runtime_evidence") or {}).get("model_device", "")).startswith("cuda")
        and str((item.get("runtime_evidence") or {}).get("output_device", "")).startswith("cuda")
        for item in processes
    )
    process_pids = [int((item.get("runtime_evidence") or {}).get("provider_pid", 0)) for item in processes]

    quantiles = response.get("quantiles") or {}
    checks = {
        "response_status_ok": response.get("status") == "OK",
        "response_phase_predict": response.get("phase") == "predict",
        "model_identity_id": model_identity.get("model_id") == EXPECTED_MODEL_ID,
        "model_identity_repo": model_identity.get("repo_id") == EXPECTED_REPO_ID,
        "model_identity_revision": model_identity.get("model_revision") == EXPECTED_MODEL_REVISION,
        "model_identity_class": model_identity.get("model_class") == EXPECTED_MODEL_CLASS,
        "model_identity_parameter_count": model_identity.get("model_parameter_count") == EXPECTED_MODEL_PARAMETER_COUNT,
        "requested_device_cuda": runtime.get("requested_device") == "cuda",
        "execution_device_cuda": str(runtime.get("execution_device", "")).startswith("cuda"),
        "model_device_cuda": str(runtime.get("model_device", "")).startswith("cuda"),
        "output_device_cuda": str(runtime.get("output_device", "")).startswith("cuda"),
        "positive_peak_vram": int(runtime.get("peak_vram_bytes", 0)) > 0,
        "external_gpu_pid_captured": runtime.get("external_gpu_pid_captured") is True,
        "cpu_fallback_false": runtime.get("cpu_fallback") is False,
        "runtime_scope_full_inference": runtime.get("runtime_scope") == "FULL_INFERENCE",
        "two_process_count": len(processes) == 2,
        "two_process_distinct_pid": len(process_pids) == 2 and min(process_pids) > 0 and len(set(process_pids)) == 2,
        "two_process_gpu_evidence": process_gpu_ok,
        "two_process_exact_replay": replay.get("exact_equal") is True,
        "snapshot_revision": snapshot.get("revision") == EXPECTED_MODEL_REVISION,
        "snapshot_weight_sha": ((snapshot.get("files") or {}).get("model.safetensors") or {}).get("sha256") == EXPECTED_MODEL_SHA256,
        "snapshot_weight_size": ((snapshot.get("files") or {}).get("model.safetensors") or {}).get("size_bytes") == EXPECTED_MODEL_SIZE,
        "input_shape": artifact.get("input_shape") == [1, 1, 128],
        "output_shape": artifact.get("output_shape") == [9, 1, 1, 1],
        "output_finite": artifact.get("output_finite") is True,
        "quantile_monotonicity": artifact.get("quantile_monotonicity") is True,
        "effective_native_shape": effective.get("native_shape") == [9, 1, 1, 1],
        "effective_actuals_unused": effective.get("actuals_used") is False,
        "point_forecast_shape": isinstance(response.get("point_forecast"), list)
        and len(response.get("point_forecast")) == 1
        and isinstance(response.get("point_forecast")[0], list)
        and len(response.get("point_forecast")[0]) == 1,
        "quantile_count": isinstance(quantiles, dict) and len(quantiles) == 9,
        "response_values_finite": all_finite(response.get("point_forecast")) and all_finite(quantiles),
        "native_first_shape": native.get("first_shape") == [9, 1, 1, 1],
        "native_second_shape": native.get("second_shape") == [9, 1, 1, 1],
        "native_finite": native.get("first_finite") is True and native.get("second_finite") is True,
        "native_exact_equal": native.get("exact_equal") is True,
    }
    checks["all_critical_checks_pass"] = all(checks.values())
    return {
        "checks": checks,
        "provider_pids": process_pids,
        "runtime_evidence": runtime,
        "gpu_process_evidence": [item.get("gpu_evidence") for item in processes],
        "replay": replay,
        "native_output": native,
        "point_forecast": response.get("point_forecast"),
        "quantiles": quantiles,
        "effective_arguments": effective,
    }


def local_manifest() -> None:
    manifest: list[dict[str, Any]] = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            manifest.append(
                {
                    "path": str(path.relative_to(LOCAL_OUT)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    dump_json(LOCAL_OUT / "ARTIFACT_MANIFEST.json", {"schema_version": 1, "artifacts": manifest})
    lines = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{sha256_file(path)}  {path}")
    (LOCAL_OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish(summary: dict[str, Any]) -> str:
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("REFUSE_TO_PUBLISH_NON_VERIFIED_PHASE4H")
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    HANDOFF_OUT.mkdir(parents=True, exist_ok=True)

    allowed_suffixes = {".json", ".jsonl", ".md", ".log", ".txt", ".tsv"}
    for src in sorted(LOCAL_OUT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(LOCAL_OUT)
        if src.suffix.lower() == ".npy":
            continue
        if src.suffix.lower() not in allowed_suffixes and src.name != "SHA256SUMS":
            continue
        dst = HANDOFF_OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    validation = summary["validation"]
    runtime = summary["runtime"]
    report = HANDOFF_OUT / "PHASE4H_REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# Phase 4H — Toto 2.0 4M Python 3.12 CUDA runtime smoke",
                "",
                f"- status: **{summary['status']}**",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                f"- environment declaration: `{ENV_NAME}`",
                f"- selected reusable runtime: `{RUNTIME}`",
                f"- Python: `{runtime.get('python')}`",
                f"- Torch: `{runtime.get('torch')}`",
                f"- Torch CUDA: `{runtime.get('torch_cuda')}`",
                f"- toto-2: `{runtime.get('toto_2')}`",
                f"- toto-models: `{runtime.get('toto_models')}`",
                f"- model: `{EXPECTED_REPO_ID}`",
                f"- pinned revision: `{EXPECTED_MODEL_REVISION}`",
                f"- parameter count: `{EXPECTED_MODEL_PARAMETER_COUNT}`",
                "- request device: `cuda`",
                "- request dtype contract: `float32`",
                "- lifecycle: CHECKPOINT LOAD → READY/GPU PID CAPTURE → FULL INFERENCE, repeated in two isolated processes",
                f"- provider PIDs: `{validation.get('provider_pids')}`",
                f"- execution device: `{validation['runtime_evidence'].get('execution_device')}`",
                f"- model device: `{validation['runtime_evidence'].get('model_device')}`",
                f"- output device: `{validation['runtime_evidence'].get('output_device')}`",
                f"- peak VRAM bytes: `{validation['runtime_evidence'].get('peak_vram_bytes')}`",
                "- CPU fallback: `False`",
                "- network model download: **disabled/offline**",
                "- input: deterministic synthetic runtime fixture; no actual/holdout opened",
                "- ranking: **non-ranking runtime smoke**; formal forecasting evaluation remains Phase 6",
                "",
                "## Critical checks",
                "",
                *[f"- {key}: `{value}`" for key, value in validation["checks"].items()],
                "",
                "## Interpretation",
                "",
                "This phase certifies real Toto 2.0 4M checkpoint loading and CUDA inference in the Phase 3D-selected reusable Python 3.12 runtime. Availability or CUDA visibility alone is not accepted as success. Accuracy, lottery-domain quality, and argument-effectiveness ranking are intentionally outside this Phase 4 scope.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text("utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff.setdefault("completed_phases", {})["phase4h"] = "VERIFIED"
    handoff["current_phase"] = "phase4_complete_phase5_next"
    handoff["phase4h"] = summary
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    progress = handoff.get("estimated_progress_percent", "unknown")
    progress_line = (
        f"- estimated progress: `{progress}%`"
        if isinstance(progress, (int, float))
        else f"- estimated progress: `{progress}`"
    )
    current = HANDOFF / "CURRENT_STATUS.md"
    current.write_text(
        "\n".join(
            [
                "# Loto Forecast Runtime Audit Handoff",
                "",
                f"Updated: {datetime.now().astimezone().isoformat()}",
                "",
                "## Current overall status",
                "",
                progress_line,
                "- Phase 4A Darts GPU smoke: `VERIFIED`",
                "- Phase 4B GluonTS latest P6 lifecycle: `VERIFIED`",
                "- Phase 4C GluonTS compat P6 lifecycle: `VERIFIED`",
                "- Phase 4D Darts no-torch CPU lifecycle: `VERIFIED`",
                "- Phase 4E sktime classic Python 3.12 CPU lifecycle: `VERIFIED`",
                "- Phase 4F sktime core Python 3.13 CPU lifecycle: `VERIFIED`",
                "- Phase 4G StatsForecast Python 3.13 CPU lifecycle: `VERIFIED`",
                "- Phase 4H Toto 2.0 4M Python 3.12 CUDA lifecycle: `VERIFIED`",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 4H",
                "",
                f"- selected runtime: `{RUNTIME}`",
                f"- Python: `{runtime.get('python')}`",
                f"- Torch: `{runtime.get('torch')}` / CUDA `{runtime.get('torch_cuda')}`",
                f"- Toto packages: `toto-2={runtime.get('toto_2')}`, `toto-models={runtime.get('toto_models')}`",
                f"- model: `{EXPECTED_REPO_ID}` @ `{EXPECTED_MODEL_REVISION}`",
                "- requested/execution contract: `CUDA full inference`",
                f"- provider GPU PIDs: `{validation.get('provider_pids')}`",
                f"- peak VRAM bytes: `{validation['runtime_evidence'].get('peak_vram_bytes')}`",
                "- CPU fallback: `False`",
                "- two-process exact replay: `True`",
                "- dependency/lock mutation: `False`",
                "- accuracy ranking: `False` (Phase 6 remains pending)",
                "",
                "## Next",
                "",
                "Phase 4 ready queue is complete. Continue with Phase 5 argument-effectiveness validation before Phase 6 all-model/all-game accuracy evaluation.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    file_sizes = HANDOFF / "FILE_SIZES.tsv"
    rows: list[tuple[int, Path]] = []
    for path in HANDOFF.rglob("*"):
        if path.is_file() and path != file_sizes:
            rows.append((path.stat().st_size, path))
    file_sizes.write_text(
        "".join(f"{size}\t{path}\n" for size, path in sorted(rows, reverse=True)),
        encoding="utf-8",
    )
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")

    sums_path = HANDOFF / "SHA256SUMS"
    lines = []
    for path in sorted(HANDOFF.rglob("*")):
        if path.is_file() and path != sums_path:
            lines.append(f"{sha256_file(path)}  {path.relative_to(HANDOFF_WT)}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    git_output(["add", "handoff"])
    check = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--check"], timeout=60)
    if check.returncode != 0:
        run(["git", "-C", str(HANDOFF_WT), "reset"], timeout=30)
        raise RuntimeError(f"STAGED_DIFF_CHECK_FAILED:{check.stdout}:{check.stderr}")

    diff = run(
        ["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--no-ext-diff", "-U0"],
        timeout=120,
    )
    added = "\n".join(
        line for line in diff.stdout.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    secret_pattern = re.compile(
        r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
        re.IGNORECASE,
    )
    if secret_pattern.search(added):
        run(["git", "-C", str(HANDOFF_WT), "reset"], timeout=30)
        raise RuntimeError("POTENTIAL_SECRET_IN_STAGED_DIFF")

    staged = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"], timeout=30)
    if staged.returncode == 1:
        commit = run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 4H Toto2 4M smoke {RUN_ID}",
            ],
            timeout=120,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED:{commit.stderr.strip()}")
    elif staged.returncode != 0:
        raise RuntimeError("STAGED_DIFF_QUERY_FAILED")

    push = run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=180)
    if push.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED:{push.stderr.strip()}")
    git_output(["fetch", "origin", BRANCH])
    local = git_output(["rev-parse", "HEAD"])
    remote = git_output(["rev-parse", f"origin/{BRANCH}"])
    if local != remote:
        raise RuntimeError(f"HANDOFF_REMOTE_HEAD_MISMATCH:local={local}:remote={remote}")
    if git_output(["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_DIRTY_AFTER_PUBLISH")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "PHASE4H_TOTO2_4M_PY312_CUDA_LIFECYCLE",
        "run_id": RUN_ID,
        "status": "FAILED",
        "source_sha": EXPECTED_SOURCE_SHA,
        "environment": ENV_NAME,
        "selected_runtime": str(ROOT / ".runtime-envs/toto"),
        "scope": "Toto 2.0 4M real-checkpoint CUDA full-inference lifecycle smoke",
        "formal_runtime_certification": False,
        "dependencies_modified": False,
        "lockfile_modified": False,
        "accuracy_ranking": False,
    }
    try:
        source_gate()
        handoff_sync()
        lane = prerequisite_gate()
        runtime = runtime_probe()
        contract = environment_contract()
        gpu_before = gpu_inventory()
        snapshot, snapshot_evidence, attempts = resolve_snapshot()
        dump_json(
            LOCAL_OUT / "snapshot-discovery.json",
            {"selected": str(snapshot), "verified": True, "attempts": attempts},
        )
        dump_json(LOCAL_OUT / "snapshot-evidence.json", snapshot_evidence)
        request = build_request(snapshot, runtime)
        response = run_certification(snapshot)
        native = inspect_native_outputs()
        validation = validate_response(response, native)
        if not validation["checks"]["all_critical_checks_pass"]:
            failed = [key for key, value in validation["checks"].items() if value is not True]
            raise RuntimeError(f"TOTO2_LIFECYCLE_VALIDATION_FAILED:{failed}")
        gpu_after = gpu_inventory()

        output_lock = {
            "locked_at_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "runtime-smoke-output-lock-not-prospective-accuracy",
            "request_sha256": sha256_file(REQUEST_PATH),
            "response_sha256": sha256_file(RESPONSE_PATH),
            "native_output_sha256": native["first_sha256"],
            "two_process_native_exact_equal": native["exact_equal"],
        }
        dump_json(LOCAL_OUT / "runtime-output-lock.json", output_lock)

        summary.update(
            {
                "status": "VERIFIED",
                "formal_runtime_certification": True,
                "lane": lane,
                "runtime": runtime,
                "environment_contract": contract,
                "gpu_inventory_before": gpu_before,
                "gpu_inventory_after": gpu_after,
                "snapshot": snapshot_evidence,
                "snapshot_path": str(snapshot),
                "request_contract": {
                    "device": request["device"],
                    "dtype": request["dtype"],
                    "context_length": request["context_length"],
                    "prediction_length": request["prediction_length"],
                    "decode_block_size": request["decode_block_size"],
                    "series_layout": request["series_layout"],
                    "synthetic_runtime_fixture": True,
                    "actuals_used": False,
                    "local_files_only": True,
                },
                "validation": validation,
                "runtime_output_lock": output_lock,
                "device_policy": {
                    "requested": "cuda",
                    "gpu_execution_claimed": True,
                    "external_provider_pid_required": True,
                    "positive_vram_required": True,
                    "cpu_fallback": False,
                    "runtime_scope": "FULL_INFERENCE",
                },
                "dataset_policy": {
                    "kind": "deterministic_synthetic_runtime_fixture",
                    "accuracy_ranking": False,
                    "holdout_opened": False,
                    "prospective_actual_known": False,
                    "metrics": "NOT_APPLICABLE_PHASE4_RUNTIME_ONLY",
                },
            }
        )
        dump_json(LOCAL_OUT / "summary.json", summary)
        local_manifest()
        head = publish(summary)
        print("=" * 60)
        print("PHASE4H_TOTO2_4M_SMOKE=VERIFIED")
        print(f"HANDOFF_HEAD={head}")
        print(f"SUMMARY={HANDOFF_OUT / 'summary.json'}")
        print(f"REPORT={HANDOFF_OUT / 'PHASE4H_REPORT.md'}")
        print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 4H結果を確認してPhase 5へ進めてください")
        print("=" * 60)
        return 0
    except Exception as exc:
        summary["status"] = "FAILED"
        summary["formal_runtime_certification"] = False
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)
        dump_json(LOCAL_OUT / "summary.json", summary)
        local_manifest()
        print("=" * 60)
        print("PHASE4H_TOTO2_4M_SMOKE=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print(f"LOCAL_SUMMARY={LOCAL_OUT / 'summary.json'}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 60)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
