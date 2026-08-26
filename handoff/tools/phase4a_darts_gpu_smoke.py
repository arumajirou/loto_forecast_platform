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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
RUNTIME = ROOT / "environments/darts-torch/.venv/bin/python"
PROVIDER = SOURCE_WT / "scripts/run_darts_provider.py"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase4a-darts-gpu-smoke-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase4a"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_output(args: list[str]) -> str:
    proc = run(["git", "-C", str(HANDOFF_WT), *args], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def source_gate() -> None:
    proc = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"])
    if proc.returncode != 0 or proc.stdout.strip() != EXPECTED_SOURCE_SHA:
        raise RuntimeError("SOURCE_SHA_GATE_FAILED")
    proc = run(["git", "-C", str(SOURCE_WT), "status", "--porcelain"])
    if proc.returncode != 0 or proc.stdout.strip():
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
        raise RuntimeError(f"HANDOFF_PULL_FAILED: {proc.stderr.strip()}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def phase3d_gate() -> dict[str, str]:
    summary = json.loads((HANDOFF / "phase3d/summary.json").read_text(encoding="utf-8"))
    if summary.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError("PHASE3D_SOURCE_SHA_MISMATCH")
    if summary.get("phase4_smoke_allowed_count", 0) < 1:
        raise RuntimeError("PHASE4_READY_QUEUE_EMPTY")
    ready = read_tsv(HANDOFF / "phase3d/phase4-ready-queue.tsv")
    row = next((item for item in ready if item.get("environment") == "environments/darts-torch"), None)
    if not row or row.get("phase4_smoke_allowed") != "True":
        raise RuntimeError("DARTS_TORCH_NOT_PHASE4_READY")
    if row.get("lane") != "CURRENT_MODERN_GPU_CANDIDATE":
        raise RuntimeError("DARTS_TORCH_NOT_MODERN_GPU_CANDIDATE")
    return row


def nvidia_state() -> dict[str, Any]:
    proc = run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=15,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def gpu_used_mib() -> int | None:
    proc = run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        timeout=15,
    )
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip().splitlines()[0].strip())
    except Exception:
        return None


def torch_probe() -> dict[str, Any]:
    code = r'''
import json
import torch
p = {
  "torch_version": str(torch.__version__),
  "cuda_build": str(torch.version.cuda),
  "cuda_available": bool(torch.cuda.is_available()),
  "device_count": int(torch.cuda.device_count()),
  "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
  "compute_capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
  "arch_list": list(torch.cuda.get_arch_list()) if hasattr(torch.cuda, "get_arch_list") else [],
}
if torch.cuda.is_available():
    x = torch.arange(4096, device="cuda", dtype=torch.float32).reshape(64, 64)
    y = x @ x.T
    torch.cuda.synchronize()
    p["cuda_tensor_device"] = str(x.device)
    p["cuda_matmul_finite"] = bool(torch.isfinite(y).all().item())
print(json.dumps(p))
'''
    proc = run([str(RUNTIME), "-I", "-c", code], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"TORCH_PROBE_FAILED: {proc.stderr.strip()}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if not payload.get("cuda_available") or not payload.get("cuda_matmul_finite"):
        raise RuntimeError("TORCH_CUDA_GATE_FAILED")
    return payload


def candidate_data_paths() -> list[Path]:
    explicit = os.environ.get("LOTO_PHASE4_DATA")
    result: list[Path] = []
    if explicit:
        result.append(Path(explicit))
    roots = [
        ROOT / "data",
        ROOT / "dataset",
        ROOT / "datasets",
        ROOT / "raw",
        ROOT.parent / "data",
        ROOT.parent / "datasets",
    ]
    skip_parts = {".git", ".venv", ".runtime-envs", "artifacts", "worktrees", "node_modules"}
    for base in roots:
        if not base.exists():
            continue
        for current, dirs, files in os.walk(base):
            current_path = Path(current)
            dirs[:] = [d for d in dirs if d not in skip_parts]
            if any(part in skip_parts for part in current_path.parts):
                continue
            for name in files:
                if name.lower().endswith((".csv", ".parquet")):
                    result.append(current_path / name)
    dedup: list[Path] = []
    seen: set[str] = set()
    for path in result:
        key = os.path.abspath(str(path))
        if key not in seen:
            seen.add(key)
            dedup.append(path)
    return dedup


def inspect_columns(path: Path) -> list[str] | None:
    try:
        if path.suffix.lower() == ".csv":
            import pandas as pd
            return list(pd.read_csv(path, nrows=2).columns)
        import pandas as pd
        return list(pd.read_parquet(path).columns)
    except Exception:
        return None


def choose_real_data() -> tuple[Path, str, list[str]]:
    draw_names = ("draw_no", "draw", "round", "draw_number")
    ranked: list[tuple[int, Path, str, list[str]]] = []
    for path in candidate_data_paths():
        cols = inspect_columns(path)
        if not cols:
            continue
        draw_col = next((name for name in draw_names if name in cols), None)
        if draw_col is None:
            continue
        positions = []
        i = 1
        while f"n{i}" in cols:
            positions.append(f"n{i}")
            i += 1
        if not positions:
            continue
        score = len(positions) * 100
        lowered = path.name.lower()
        if any(x in lowered for x in ("numbers4", "numbers3", "loto7", "loto6", "miniloto")):
            score += 50
        ranked.append((score, path, draw_col, positions))
    if not ranked:
        raise RuntimeError(
            "REAL_DATA_NOT_FOUND: set LOTO_PHASE4_DATA to a CSV/Parquet with draw_no and n1..nN"
        )
    ranked.sort(key=lambda x: (-x[0], str(x[1])))
    _, path, draw_col, positions = ranked[0]
    return path, draw_col, positions


def prepare_smoke_input(path: Path, draw_col: str, position_cols: list[str]) -> dict[str, Any]:
    import pandas as pd

    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        frame = pd.read_parquet(path)
    use_positions = position_cols[: min(4, len(position_cols))]
    required = [draw_col, *use_positions]
    frame = frame[required].copy()
    frame[draw_col] = pd.to_numeric(frame[draw_col], errors="coerce")
    for col in use_positions:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna().copy()
    frame[draw_col] = frame[draw_col].astype(int)
    frame = frame.drop_duplicates(subset=[draw_col], keep="first")

    draws = frame[draw_col].to_numpy()
    best_start = 0
    best_end = 0
    start = 0
    for idx in range(1, len(draws) + 1):
        if idx == len(draws) or int(draws[idx]) != int(draws[idx - 1]) + 1:
            if idx - start > best_end - best_start:
                best_start, best_end = start, idx
            start = idx
    contiguous = frame.iloc[best_start:best_end].copy()
    if len(contiguous) < 48:
        raise RuntimeError(f"REAL_DATA_CONTIGUOUS_ROWS_TOO_SHORT: {len(contiguous)}")
    contiguous = contiguous.tail(min(128, len(contiguous))).copy()
    output = LOCAL_OUT / "smoke-input.csv"
    contiguous.to_csv(output, index=False)
    values = contiguous[use_positions].to_numpy(dtype=float)
    return {
        "source_path": str(path),
        "source_sha256": sha256_file(path),
        "derived_path": str(output),
        "derived_sha256": sha256_file(output),
        "draw_no_col": draw_col,
        "position_columns": use_positions,
        "rows": len(contiguous),
        "first_draw": int(contiguous[draw_col].iloc[0]),
        "last_draw": int(contiguous[draw_col].iloc[-1]),
        "min_value": int(math.floor(float(values.min()))),
        "max_value": int(math.ceil(float(values.max()))),
    }


def provider_call(request_path: Path, response_path: Path, data_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [str(RUNTIME), str(PROVIDER), "--request", str(request_path), "--response", str(response_path)]
    if data_path is not None:
        cmd += ["--data", str(data_path)]
    return run(cmd, timeout=180)


def discover_models(data_meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    request = {
        "schema_version": 1,
        "run_id": f"phase4a-darts-discover-{RUN_ID}",
        "mode": "discover",
        "geometry": {
            "game_id": "phase4a-real-data",
            "positions": len(data_meta["position_columns"]),
            "min_value": data_meta["min_value"],
            "max_value": data_meta["max_value"],
            "draw_no_col": data_meta["draw_no_col"],
            "position_prefix": "n",
        },
        "runtime": "torch",
        "device": "cuda",
        "seed": 1,
        "artifact_dir": str(LOCAL_OUT / "discover-artifacts"),
    }
    request_path = LOCAL_OUT / "discover-request.json"
    response_path = LOCAL_OUT / "discover-response.json"
    dump_json(request_path, request)
    proc = provider_call(request_path, response_path)
    (LOCAL_OUT / "discover.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "discover.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0 or not response_path.exists():
        raise RuntimeError("DARTS_DISCOVERY_PROCESS_FAILED")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    if response.get("status") != "SUCCEEDED":
        raise RuntimeError(f"DARTS_DISCOVERY_FAILED: {response}")
    inventory = response.get("model_inventory") or []
    preferred = ["DLinearModel", "NLinearModel", "BlockRNNModel", "RNNModel", "NBEATSModel"]
    for name in preferred:
        row = next((x for x in inventory if x.get("public_name") == name), None)
        if row and row.get("status") == "IMPORTED":
            return name, row
    raise RuntimeError("NO_IMPORTED_DARTS_TORCH_SMOKE_MODEL")


def model_signature(public_name: str) -> dict[str, Any]:
    code = r'''
import inspect, json, sys
from darts import models
cls = getattr(models, sys.argv[1])
sig = inspect.signature(cls)
params = {}
for name, p in sig.parameters.items():
    params[name] = {
        "kind": str(p.kind),
        "required": p.default is inspect._empty,
        "default": None if p.default is inspect._empty else repr(p.default),
    }
print(json.dumps({"signature": str(sig), "parameters": params}))
'''
    proc = run([str(RUNTIME), "-I", "-c", code, public_name], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"MODEL_SIGNATURE_FAILED: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def build_model_args(signature: dict[str, Any]) -> dict[str, Any]:
    params = signature.get("parameters", {})
    has_kwargs = any(v.get("kind") == "VAR_KEYWORD" for v in params.values())

    def accepted(name: str) -> bool:
        return name in params or has_kwargs

    desired: dict[str, Any] = {
        "input_chunk_length": 12,
        "output_chunk_length": 1,
        "n_epochs": 2,
        "batch_size": 16,
        "random_state": 1,
        "force_reset": True,
        "save_checkpoints": False,
        "pl_trainer_kwargs": {
            "accelerator": "gpu",
            "devices": 1,
            "logger": False,
            "enable_checkpointing": False,
            "enable_progress_bar": False,
        },
    }
    return {k: v for k, v in desired.items() if accepted(k)}


def child_pids(root_pid: int) -> set[int]:
    proc = run(["ps", "-eo", "pid=,ppid="], timeout=10)
    if proc.returncode != 0:
        return {root_pid}
    children: dict[int, list[int]] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    result = {root_pid}
    stack = [root_pid]
    while stack:
        parent = stack.pop()
        for child in children.get(parent, []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def gpu_process_rows() -> list[dict[str, Any]]:
    proc = run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        timeout=10,
    )
    rows: list[dict[str, Any]] = []
    if proc.returncode != 0:
        return rows
    for line in proc.stdout.splitlines():
        parts = [x.strip() for x in line.split(",", 2)]
        if len(parts) != 3:
            continue
        try:
            rows.append({"pid": int(parts[0]), "process_name": parts[1], "used_memory_mib": int(parts[2])})
        except ValueError:
            pass
    return rows


def fit_predict_smoke(public_name: str, signature: dict[str, Any], data_meta: dict[str, Any]) -> dict[str, Any]:
    model_args = build_model_args(signature)
    request = {
        "schema_version": 1,
        "run_id": f"phase4a-darts-gpu-{RUN_ID}",
        "mode": "fit_predict",
        "geometry": {
            "game_id": "phase4a-real-data",
            "positions": len(data_meta["position_columns"]),
            "min_value": data_meta["min_value"],
            "max_value": data_meta["max_value"],
            "draw_no_col": data_meta["draw_no_col"],
            "position_prefix": "n",
        },
        "model": {"public_name": public_name, "module": "darts.models"},
        "series_layout": "position_local",
        "horizon": 1,
        "model_args": model_args,
        "fit_args": {},
        "predict_args": {},
        "runtime": "torch",
        "device": "cuda",
        "seed": 1,
        "timeout_seconds": 600,
        "artifact_dir": str(LOCAL_OUT / "provider-artifacts"),
        "evaluation": {
            "enabled": True,
            "holdout_size": 1,
            "tolerance": 1.0,
            "season_length": 1,
            "baselines": ["random", "fixed", "mean", "median", "last", "frequency", "seasonal_naive"],
        },
        "persistence": {"save_model": True, "verify_save_load": True, "rtol": 1e-6, "atol": 1e-6},
        "prospective": {"seal_predictions": False, "actual_known": False},
    }
    request_path = LOCAL_OUT / "request.json"
    response_path = LOCAL_OUT / "response.json"
    dump_json(request_path, request)

    stdout_path = LOCAL_OUT / "provider.stdout.log"
    stderr_path = LOCAL_OUT / "provider.stderr.log"
    cmd = [
        str(RUNTIME),
        str(PROVIDER),
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        "--data",
        data_meta["derived_path"],
    ]
    started = time.time()
    with stdout_path.open("w", encoding="utf-8") as out_f, stderr_path.open("w", encoding="utf-8") as err_f:
        proc = subprocess.Popen(cmd, stdout=out_f, stderr=err_f, text=True)
        samples: list[dict[str, Any]] = []
        peak = 0
        matched_pids: set[int] = set()
        while proc.poll() is None:
            descendants = child_pids(proc.pid)
            gpu_rows = gpu_process_rows()
            matched = [row for row in gpu_rows if row["pid"] in descendants]
            for row in matched:
                matched_pids.add(row["pid"])
                peak = max(peak, row["used_memory_mib"])
            samples.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "root_pid": proc.pid,
                    "descendants": sorted(descendants),
                    "matching_gpu_processes": matched,
                    "all_gpu_processes": gpu_rows,
                }
            )
            time.sleep(0.10)
        returncode = proc.wait(timeout=10)
    duration = time.time() - started
    with (LOCAL_OUT / "gpu-process-samples.jsonl").open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
    if not response_path.exists():
        raise RuntimeError(f"DARTS_PROVIDER_NO_RESPONSE: returncode={returncode}")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    return {
        "request": request,
        "response": response,
        "returncode": returncode,
        "duration_seconds": duration,
        "provider_root_pid": proc.pid,
        "matched_gpu_pids": sorted(matched_pids),
        "peak_matching_gpu_memory_mib": peak,
        "gpu_sample_count": len(samples),
    }


def validate_result(result: dict[str, Any], data_meta: dict[str, Any]) -> dict[str, Any]:
    response = result["response"]
    checks: dict[str, bool] = {}
    checks["process_exit_zero"] = result["returncode"] == 0
    checks["response_succeeded"] = response.get("status") == "SUCCEEDED"
    predictions = response.get("predictions")
    positions = len(data_meta["position_columns"])
    checks["prediction_shape"] = (
        isinstance(predictions, list)
        and len(predictions) == positions
        and all(isinstance(row, list) and len(row) == 1 for row in predictions)
    )
    finite = False
    if checks["prediction_shape"]:
        try:
            finite = all(math.isfinite(float(row[0])) for row in predictions)
        except Exception:
            finite = False
    checks["prediction_finite"] = finite
    metrics = response.get("metrics") or {}
    required_metrics = {
        "hit_at_plus_minus_1",
        "position_hit_at_plus_minus_1",
        "all_position_hit_at_plus_minus_1",
        "mae",
        "mse",
        "rmse",
    }
    checks["metrics_complete"] = required_metrics.issubset(metrics)
    baselines = response.get("baseline_metrics") or {}
    required_baselines = {"random", "fixed", "mean", "median", "last", "frequency", "seasonal_naive"}
    checks["baselines_complete"] = required_baselines.issubset(baselines)
    cert = response.get("runtime_certification") or []
    checks["save_reload_certified"] = (
        len(cert) == positions and all(item.get("status") == "RUNTIME_CERTIFIED" for item in cert)
    )
    checks["requested_device_cuda"] = result["request"].get("device") == "cuda"
    checks["gpu_pid_observed"] = bool(result.get("matched_gpu_pids"))
    checks["gpu_vram_observed"] = int(result.get("peak_matching_gpu_memory_mib", 0)) > 0
    status = "VERIFIED" if all(checks.values()) else "FAILED"
    return {"status": status, "checks": checks}


def publish(summary: dict[str, Any]) -> str:
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    shutil.copytree(LOCAL_OUT, HANDOFF_OUT)

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff.setdefault("completed_phases", {})["phase4a"] = summary["status"]
    handoff["current_phase"] = (
        "phase4a_darts_gpu_verified_phase4b_next"
        if summary["status"] == "VERIFIED"
        else "phase4a_darts_gpu_requires_review"
    )
    handoff["estimated_progress_percent"] = 44 if summary["status"] == "VERIFIED" else 40
    handoff["phase4a"] = summary
    handoff_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

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
                f"- estimated progress: `{handoff['estimated_progress_percent']}%`",
                f"- Phase 4A Darts GPU smoke: `{summary['status']}`",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 4A",
                "",
                f"- model: `{summary.get('model_public_name')}`",
                f"- runtime: `{RUNTIME}`",
                f"- real data source: `{summary.get('data', {}).get('source_path')}`",
                f"- prediction shape/finite: `{summary.get('validation', {}).get('checks', {}).get('prediction_shape')}` / `{summary.get('validation', {}).get('checks', {}).get('prediction_finite')}`",
                f"- GPU PID observed: `{summary.get('validation', {}).get('checks', {}).get('gpu_pid_observed')}`",
                f"- peak provider VRAM MiB: `{summary.get('gpu', {}).get('peak_matching_gpu_memory_mib')}`",
                f"- save/reload certified: `{summary.get('validation', {}).get('checks', {}).get('save_reload_certified')}`",
                "",
                "## Next",
                "",
                "If VERIFIED, continue Phase 4B across the remaining ready queue. If FAILED, review Phase 4A evidence before changing dependencies.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    file_sizes = HANDOFF / "FILE_SIZES.tsv"
    rows = []
    for path in HANDOFF.rglob("*"):
        if path.is_file():
            rows.append((path.stat().st_size, path))
    file_sizes.write_text("".join(f"{size}\t{path}\n" for size, path in sorted(rows, reverse=True)), encoding="utf-8")
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")

    sums = HANDOFF / "SHA256SUMS"
    lines = []
    for path in sorted(HANDOFF.rglob("*")):
        if path.is_file() and path != sums:
            lines.append(f"{sha256_file(path)}  {path.relative_to(HANDOFF_WT)}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")

    git_output(["add", "handoff"])
    if git_output(["diff", "--cached", "--quiet"]) == "":
        pass
    # `git diff --quiet` uses return code, so invoke separately.
    diff_proc = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"], timeout=30)
    if diff_proc.returncode != 0:
        commit_proc = run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 4A Darts GPU smoke {RUN_ID}",
            ],
            timeout=120,
        )
        if commit_proc.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED: {commit_proc.stderr.strip()}")
    push_proc = run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=180)
    if push_proc.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED: {push_proc.stderr.strip()}")
    git_output(["fetch", "origin", BRANCH])
    local = git_output(["rev-parse", "HEAD"])
    remote = git_output(["rev-parse", f"origin/{BRANCH}"])
    if local != remote:
        raise RuntimeError("HANDOFF_REMOTE_VERIFY_FAILED")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    status = "FAILED"
    summary: dict[str, Any] = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "source_sha": EXPECTED_SOURCE_SHA,
        "status": "FAILED",
        "formal_runtime_certification": False,
        "scope": "Darts torch real-data GPU smoke",
    }
    try:
        source_gate()
        handoff_sync()
        lane = phase3d_gate()
        if not RUNTIME.exists() or not os.access(RUNTIME, os.X_OK):
            raise RuntimeError(f"DARTS_RUNTIME_NOT_EXECUTABLE: {RUNTIME}")
        if not PROVIDER.exists():
            raise RuntimeError(f"DARTS_PROVIDER_MISSING: {PROVIDER}")

        before = nvidia_state()
        used_before = gpu_used_mib()
        dump_json(LOCAL_OUT / "gpu-before.json", before)
        if used_before is not None and used_before > int(os.environ.get("LOTO_PHASE4_MAX_BASELINE_VRAM_MIB", "4096")):
            raise RuntimeError(f"GPU_BUSY_BASELINE_VRAM_MIB={used_before}")

        torch = torch_probe()
        dump_json(LOCAL_OUT / "torch-probe.json", torch)
        data_path, draw_col, position_cols = choose_real_data()
        data_meta = prepare_smoke_input(data_path, draw_col, position_cols)
        dump_json(LOCAL_OUT / "data-evidence.json", data_meta)

        public_name, discovery_row = discover_models(data_meta)
        signature = model_signature(public_name)
        dump_json(LOCAL_OUT / "selected-model.json", {"public_name": public_name, "discovery": discovery_row, "signature": signature})

        result = fit_predict_smoke(public_name, signature, data_meta)
        validation = validate_result(result, data_meta)
        after = nvidia_state()
        dump_json(LOCAL_OUT / "gpu-after.json", after)

        summary.update(
            {
                "status": validation["status"],
                "formal_runtime_certification": validation["status"] == "VERIFIED",
                "model_public_name": public_name,
                "runtime": str(RUNTIME),
                "provider": str(PROVIDER),
                "lane": lane,
                "torch": torch,
                "data": data_meta,
                "gpu": {
                    "baseline_used_mib": used_before,
                    "provider_root_pid": result["provider_root_pid"],
                    "matched_gpu_pids": result["matched_gpu_pids"],
                    "peak_matching_gpu_memory_mib": result["peak_matching_gpu_memory_mib"],
                    "gpu_sample_count": result["gpu_sample_count"],
                    "before": before,
                    "after": after,
                },
                "duration_seconds": result["duration_seconds"],
                "response_status": result["response"].get("status"),
                "failure_class": result["response"].get("failure_class"),
                "metrics": result["response"].get("metrics"),
                "baseline_metrics": result["response"].get("baseline_metrics"),
                "validation": validation,
            }
        )
        status = validation["status"]
    except Exception as exc:
        summary["status"] = "FAILED"
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)
        status = "FAILED"

    dump_json(LOCAL_OUT / "summary.json", summary)
    report_lines = [
        "# Phase 4A Darts GPU Smoke",
        "",
        f"- status: `{summary['status']}`",
        f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
        f"- model: `{summary.get('model_public_name', '')}`",
        f"- runtime: `{summary.get('runtime', str(RUNTIME))}`",
        f"- real data: `{summary.get('data', {}).get('source_path', '')}`",
        f"- real data rows used: `{summary.get('data', {}).get('rows', '')}`",
        f"- GPU PIDs: `{summary.get('gpu', {}).get('matched_gpu_pids', [])}`",
        f"- peak matching VRAM MiB: `{summary.get('gpu', {}).get('peak_matching_gpu_memory_mib', 0)}`",
        f"- response status: `{summary.get('response_status', '')}`",
        f"- save/reload certified: `{summary.get('validation', {}).get('checks', {}).get('save_reload_certified', False)}`",
        "",
        "## Certification boundary",
        "",
        "VERIFIED requires provider exit zero, successful fit/predict, exact position×horizon output shape, finite output, Hit@±1/MAE/MSE/RMSE metrics, all configured baselines, successful save/reload prediction equality, and provider/descendant GPU PID + VRAM evidence.",
    ]
    if summary.get("error"):
        report_lines += ["", "## Error", "", f"`{summary['error_type']}: {summary['error']}`"]
    (LOCAL_OUT / "PHASE4A_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    # Local manifest before copying into handoff.
    manifest = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name != "ARTIFACT_MANIFEST.json":
            manifest.append({"path": str(path.relative_to(LOCAL_OUT)), "size": path.stat().st_size, "sha256": sha256_file(path)})
    dump_json(LOCAL_OUT / "ARTIFACT_MANIFEST.json", {"schema_version": 1, "artifacts": manifest})

    head = publish(summary)
    print("=" * 60)
    print(f"PHASE4A_DARTS_GPU_SMOKE={status}")
    print(f"HANDOFF_HEAD={head}")
    print(f"SUMMARY={HANDOFF_OUT / 'summary.json'}")
    print(f"REPORT={HANDOFF_OUT / 'PHASE4A_REPORT.md'}")
    print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 4A結果を確認して次へ進めてください")
    print("=" * 60)
    return 0 if status == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
