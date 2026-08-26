#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
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
ENV_NAME = "environments/darts-notorch"
RUNTIME = ROOT / ENV_NAME / ".venv/bin/python"
PROVIDER = SOURCE_WT / "scripts/run_darts_provider.py"
ENV_PROJECT = SOURCE_WT / ENV_NAME
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase4d-darts-notorch-smoke-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase4d"

PREFERRED_MODELS = (
    "NaiveDrift",
    "NaiveMean",
    "NaiveSeasonal",
    "ExponentialSmoothing",
    "Theta",
    "FourTheta",
    "FFT",
    "ARIMA",
)


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
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def prerequisite_gate() -> dict[str, str]:
    phase4c = json.loads((HANDOFF / "phase4c/summary.json").read_text("utf-8"))
    if phase4c.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4C_NOT_VERIFIED")

    phase3d = json.loads((HANDOFF / "phase3d/summary.json").read_text("utf-8"))
    if phase3d.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError("PHASE3D_SOURCE_SHA_MISMATCH")
    ready = read_tsv(HANDOFF / "phase3d/phase4-ready-queue.tsv")
    row = next((item for item in ready if item.get("environment") == ENV_NAME), None)
    if row is None:
        raise RuntimeError("DARTS_NOTORCH_NOT_IN_PHASE4_READY_QUEUE")
    if row.get("phase4_smoke_allowed") != "True":
        raise RuntimeError("DARTS_NOTORCH_PHASE4_SMOKE_NOT_ALLOWED")
    if row.get("lane") != "CURRENT_CPU_LEGACY":
        raise RuntimeError(f"DARTS_NOTORCH_UNEXPECTED_LANE:{row.get('lane')}")
    return row


def runtime_probe() -> dict[str, Any]:
    if not RUNTIME.exists() or not os.access(RUNTIME, os.X_OK):
        raise RuntimeError(f"DARTS_NOTORCH_RUNTIME_MISSING:{RUNTIME}")
    code = r'''
import importlib.metadata
import importlib.util
import json
import platform
import sys


def version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None

payload = {
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "darts": version("u8darts") or version("darts"),
    "numpy": version("numpy"),
    "pandas": version("pandas"),
    "torch_installed": importlib.util.find_spec("torch") is not None,
}
if payload["torch_installed"]:
    import torch
    payload.update({
        "torch": version("torch"),
        "torch_cuda_build": str(torch.version.cuda),
        "torch_cuda_available_outer_runtime": bool(torch.cuda.is_available()),
        "torch_device_count_outer_runtime": int(torch.cuda.device_count()),
    })
print(json.dumps(payload, sort_keys=True))
'''
    proc = run([str(RUNTIME), "-I", "-c", code], timeout=60)
    (LOCAL_OUT / "runtime-probe.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "runtime-probe.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"DARTS_NOTORCH_RUNTIME_PROBE_FAILED:{proc.stderr.strip()}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if payload.get("darts") != "0.46.1":
        raise RuntimeError(f"DARTS_VERSION_MISMATCH:{payload.get('darts')}")
    if not str(payload.get("prefix", "")).endswith("/environments/darts-notorch/.venv"):
        raise RuntimeError(f"DARTS_NOTORCH_PREFIX_MISMATCH:{payload.get('prefix')}")
    return payload


def environment_contract() -> dict[str, Any]:
    pyproject = ENV_PROJECT / "pyproject.toml"
    lock_status = ENV_PROJECT / "LOCK_STATUS.md"
    if not pyproject.exists() or not lock_status.exists():
        raise RuntimeError("DARTS_NOTORCH_ENVIRONMENT_CONTRACT_MISSING")
    lock_text = lock_status.read_text("utf-8")
    return {
        "pyproject_path": str(pyproject),
        "pyproject_sha256": sha256_file(pyproject),
        "lock_status_path": str(lock_status),
        "lock_status_sha256": sha256_file(lock_status),
        "lock_status_text": lock_text,
        "uv_lock_exists": (ENV_PROJECT / "uv.lock").exists(),
        "dependencies_modified": False,
        "lockfile_modified": False,
    }


def phase4a_data_contract() -> dict[str, Any]:
    summary = json.loads((HANDOFF / "phase4a/summary.json").read_text("utf-8"))
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4A_DATA_SOURCE_NOT_VERIFIED")
    data = dict(summary.get("data") or {})
    source = Path(str(data.get("source_path", "")))
    expected_hash = str(data.get("source_sha256", ""))
    positions = list(data.get("position_columns") or [])
    draw_col = str(data.get("draw_no_col", ""))
    if not source.is_file():
        raise RuntimeError(f"PHASE4A_SOURCE_DATA_MISSING:{source}")
    actual_hash = sha256_file(source)
    if actual_hash != expected_hash:
        raise RuntimeError("PHASE4A_SOURCE_DATA_SHA256_MISMATCH")
    if not draw_col or not positions:
        raise RuntimeError("PHASE4A_DATA_SCHEMA_MISSING")
    return {
        **data,
        "source_sha256_verified": True,
        "source_sha256_actual": actual_hash,
    }


def prepare_smoke_input(data: dict[str, Any]) -> dict[str, Any]:
    source = Path(data["source_path"])
    draw_col = str(data["draw_no_col"])
    positions = list(data["position_columns"])
    if source.suffix.lower() != ".csv":
        raise RuntimeError("PHASE4D_CURRENT_IMPLEMENTATION_REQUIRES_CSV_SOURCE")

    rows: list[dict[str, str]] = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        required = [draw_col, *positions]
        missing = [name for name in required if name not in fields]
        if missing:
            raise RuntimeError(f"PHASE4D_SOURCE_COLUMNS_MISSING:{missing}")
        for raw in reader:
            try:
                draw = int(float(raw[draw_col]))
                values = [float(raw[name]) for name in positions]
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in values):
                continue
            row = {draw_col: str(draw)}
            for name, value in zip(positions, values, strict=True):
                row[name] = str(value)
            rows.append(row)

    by_draw: dict[int, dict[str, str]] = {}
    for row in rows:
        by_draw.setdefault(int(row[draw_col]), row)
    ordered = [by_draw[key] for key in sorted(by_draw)]
    if len(ordered) < 48:
        raise RuntimeError(f"PHASE4D_SOURCE_ROWS_TOO_SHORT:{len(ordered)}")

    best: list[dict[str, str]] = []
    current: list[dict[str, str]] = []
    prev: int | None = None
    for row in ordered:
        draw = int(row[draw_col])
        if prev is None or draw == prev + 1:
            current.append(row)
        else:
            if len(current) > len(best):
                best = current
            current = [row]
        prev = draw
    if len(current) > len(best):
        best = current
    if len(best) < 48:
        raise RuntimeError(f"PHASE4D_CONTIGUOUS_ROWS_TOO_SHORT:{len(best)}")
    selected = best[-min(128, len(best)):]

    output = LOCAL_OUT / "smoke-input.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[draw_col, *positions])
        writer.writeheader()
        writer.writerows(selected)

    values = [float(row[name]) for row in selected for name in positions]
    derived = {
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "derived_path": str(output),
        "derived_sha256": sha256_file(output),
        "draw_no_col": draw_col,
        "position_columns": positions,
        "rows": len(selected),
        "first_draw": int(selected[0][draw_col]),
        "last_draw": int(selected[-1][draw_col]),
        "min_value": int(math.floor(min(values))),
        "max_value": int(math.ceil(max(values))),
        "comparison_basis": "same verified source/schema/window rule as Phase 4A",
    }
    if int(data.get("rows", -1)) == derived["rows"]:
        derived["phase4a_row_count_match"] = True
    else:
        derived["phase4a_row_count_match"] = False
    return derived


def provider_env() -> dict[str, str]:
    python_path = os.pathsep.join([str(SOURCE_WT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return {
        **os.environ,
        "PYTHONPATH": python_path,
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def provider_call(
    request_path: Path,
    response_path: Path,
    *,
    data_path: Path | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        str(RUNTIME),
        str(PROVIDER),
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    ]
    if data_path is not None:
        cmd += ["--data", str(data_path)]
    return run(cmd, timeout=timeout, env=provider_env())


def discover_model(data_meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    request = {
        "schema_version": 1,
        "run_id": f"phase4d-darts-notorch-discover-{RUN_ID}",
        "mode": "discover",
        "geometry": {
            "game_id": "phase4d-real-data",
            "positions": len(data_meta["position_columns"]),
            "min_value": data_meta["min_value"],
            "max_value": data_meta["max_value"],
            "draw_no_col": data_meta["draw_no_col"],
            "position_prefix": "n",
        },
        "runtime": "notorch",
        "device": "cpu",
        "seed": 1,
        "artifact_dir": str(LOCAL_OUT / "discover-artifacts"),
    }
    request_path = LOCAL_OUT / "discover-request.json"
    response_path = LOCAL_OUT / "discover-response.json"
    dump_json(request_path, request)
    proc = provider_call(request_path, response_path, timeout=120)
    (LOCAL_OUT / "discover.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "discover.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0 or not response_path.exists():
        raise RuntimeError(f"DARTS_NOTORCH_DISCOVERY_PROCESS_FAILED:rc={proc.returncode}")
    response = json.loads(response_path.read_text("utf-8"))
    if response.get("status") != "SUCCEEDED":
        raise RuntimeError(f"DARTS_NOTORCH_DISCOVERY_FAILED:{response}")
    inventory = response.get("model_inventory") or []
    dump_json(LOCAL_OUT / "discovery-inventory.json", inventory)
    for name in PREFERRED_MODELS:
        row = next((item for item in inventory if item.get("public_name") == name), None)
        if row and row.get("status") == "IMPORTED":
            return name, row
    imported = [item.get("public_name") for item in inventory if item.get("status") == "IMPORTED"]
    raise RuntimeError(f"NO_CLASSIC_DARTS_NOTORCH_MODEL_IMPORTED:{imported}")


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
    if proc.returncode != 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = [value.strip() for value in line.split(",", 2)]
        if len(parts) != 3:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[0]),
                    "process_name": parts[1],
                    "used_memory_mib": int(parts[2]),
                }
            )
        except ValueError:
            continue
    return rows


def fit_predict_smoke(public_name: str, data_meta: dict[str, Any]) -> dict[str, Any]:
    request = {
        "schema_version": 1,
        "run_id": f"phase4d-darts-notorch-{RUN_ID}",
        "mode": "fit_predict",
        "geometry": {
            "game_id": "phase4d-real-data",
            "positions": len(data_meta["position_columns"]),
            "min_value": data_meta["min_value"],
            "max_value": data_meta["max_value"],
            "draw_no_col": data_meta["draw_no_col"],
            "position_prefix": "n",
        },
        "model": {"public_name": public_name, "module": "darts.models"},
        "series_layout": "position_local",
        "horizon": 1,
        "model_args": {},
        "fit_args": {},
        "predict_args": {},
        "runtime": "notorch",
        "device": "cpu",
        "seed": 1,
        "timeout_seconds": 600,
        "artifact_dir": str(LOCAL_OUT / "provider-artifacts"),
        "evaluation": {
            "enabled": True,
            "holdout_size": 1,
            "tolerance": 1.0,
            "season_length": 1,
            "baselines": [
                "random",
                "fixed",
                "mean",
                "median",
                "last",
                "frequency",
                "seasonal_naive",
            ],
        },
        "persistence": {
            "save_model": True,
            "verify_save_load": True,
            "rtol": 1e-6,
            "atol": 1e-6,
        },
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
    samples: list[dict[str, Any]] = []
    matched_pids: set[int] = set()
    with stdout_path.open("w", encoding="utf-8") as out_f, stderr_path.open("w", encoding="utf-8") as err_f:
        proc = subprocess.Popen(
            cmd,
            stdout=out_f,
            stderr=err_f,
            text=True,
            env=provider_env(),
        )
        while proc.poll() is None:
            descendants = child_pids(proc.pid)
            gpu_rows = gpu_process_rows()
            matched = [row for row in gpu_rows if row["pid"] in descendants]
            matched_pids.update(row["pid"] for row in matched)
            samples.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "root_pid": proc.pid,
                    "descendants": sorted(descendants),
                    "matching_gpu_processes": matched,
                }
            )
            time.sleep(0.05)
        returncode = proc.wait(timeout=10)
    duration = time.time() - started
    with (LOCAL_OUT / "gpu-process-samples.jsonl").open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")

    if not response_path.exists():
        raise RuntimeError(f"DARTS_NOTORCH_PROVIDER_NO_RESPONSE:rc={returncode}")
    response = json.loads(response_path.read_text("utf-8"))
    return {
        "request": request,
        "response": response,
        "returncode": returncode,
        "duration_seconds": duration,
        "provider_root_pid": proc.pid,
        "matched_gpu_pids": sorted(matched_pids),
        "gpu_sample_count": len(samples),
        "cuda_visible_devices_for_provider": "",
    }


def validate_result(result: dict[str, Any], data_meta: dict[str, Any]) -> dict[str, Any]:
    response = result["response"]
    positions = len(data_meta["position_columns"])
    predictions = response.get("predictions")
    checks: dict[str, bool] = {
        "process_exit_zero": result["returncode"] == 0,
        "response_succeeded": response.get("status") == "SUCCEEDED",
        "requested_runtime_notorch": result["request"].get("runtime") == "notorch",
        "requested_device_cpu": result["request"].get("device") == "cpu",
        "provider_cuda_hidden": result.get("cuda_visible_devices_for_provider") == "",
        "no_provider_gpu_pid_observed": not result.get("matched_gpu_pids"),
    }
    checks["prediction_shape"] = (
        isinstance(predictions, list)
        and len(predictions) == positions
        and all(isinstance(row, list) and len(row) == 1 for row in predictions)
    )
    checks["prediction_finite"] = False
    if checks["prediction_shape"]:
        try:
            checks["prediction_finite"] = all(math.isfinite(float(row[0])) for row in predictions)
        except Exception:
            checks["prediction_finite"] = False

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
    required_baselines = {
        "random",
        "fixed",
        "mean",
        "median",
        "last",
        "frequency",
        "seasonal_naive",
    }
    checks["baselines_complete"] = required_baselines.issubset(baselines)
    cert = response.get("runtime_certification") or []
    checks["save_reload_certified"] = (
        len(cert) == positions
        and all(item.get("status") == "RUNTIME_CERTIFIED" for item in cert)
    )
    checks["all_critical_checks_pass"] = all(checks.values())
    return {
        "status": "VERIFIED" if checks["all_critical_checks_pass"] else "FAILED",
        "checks": checks,
    }


def write_local_report(summary: dict[str, Any]) -> None:
    report = LOCAL_OUT / "PHASE4D_REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# Phase 4D — Darts no-torch CPU lifecycle smoke",
                "",
                f"- status: **{summary['status']}**",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                f"- environment: `{ENV_NAME}`",
                f"- runtime: `{RUNTIME}`",
                f"- Darts: `{summary.get('runtime_probe', {}).get('darts')}`",
                f"- model: `{summary.get('model_public_name')}`",
                "- formal runtime/device contract: `runtime=notorch`, `device=cpu`",
                "- provider CUDA visibility: hidden (`CUDA_VISIBLE_DEVICES=\"\"`)",
                f"- provider/descendant GPU PIDs observed: `{summary.get('execution', {}).get('matched_gpu_pids', [])}`",
                "- lifecycle: fit -> predict -> save -> load -> predict equality",
                "- data: same verified historical source/window rule as Phase 4A",
                "- metrics are smoke evidence only; final model ranking remains Phase 6",
                "- dependency/lock files modified: **False**",
                "",
                "## Critical checks",
                "",
                *[
                    f"- {key}: `{value}`"
                    for key, value in summary.get("validation", {}).get("checks", {}).items()
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def local_manifest() -> None:
    rows: list[dict[str, Any]] = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name != "ARTIFACT_MANIFEST.json":
            rows.append(
                {
                    "path": str(path.relative_to(LOCAL_OUT)),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    dump_json(LOCAL_OUT / "ARTIFACT_MANIFEST.json", {"schema_version": 1, "artifacts": rows})


def publish(summary: dict[str, Any]) -> str:
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("REFUSE_TO_PUBLISH_NON_VERIFIED_PHASE4D")
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    HANDOFF_OUT.mkdir(parents=True, exist_ok=True)

    allowed_suffixes = {".json", ".jsonl", ".md", ".log", ".txt", ".tsv"}
    for src in sorted(LOCAL_OUT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(LOCAL_OUT)
        if rel.name == "smoke-input.csv" or "models" in rel.parts:
            continue
        if src.suffix.lower() not in allowed_suffixes:
            continue
        dst = HANDOFF_OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text("utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff.setdefault("completed_phases", {})["phase4d"] = "VERIFIED"
    handoff["current_phase"] = "phase4d_darts_notorch_verified_sktime_classic_next"
    handoff["phase4d"] = summary
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
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 4D",
                "",
                f"- runtime: `{RUNTIME}`",
                f"- Darts: `{summary.get('runtime_probe', {}).get('darts')}`",
                f"- model: `{summary.get('model_public_name')}`",
                "- runtime contract: `notorch`",
                "- device contract: `cpu`",
                "- CUDA hidden from provider: `True`",
                f"- provider GPU PIDs: `{summary.get('execution', {}).get('matched_gpu_pids', [])}`",
                "- save/reload certified: `True`",
                "- dependency/lock mutation: `False`",
                "- accuracy ranking: `False` (Phase 6 remains pending)",
                "",
                "## Next",
                "",
                "Continue with `environments/sktime-classic-py312`, then `environments/sktime-core-py313`, `environments/statsforecast-py313`, and finally `environments/toto2-4m-py312` from the Phase 4 ready queue.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    file_sizes = HANDOFF / "FILE_SIZES.tsv"
    rows: list[tuple[int, Path]] = []
    for path in HANDOFF.rglob("*"):
        if path.is_file():
            rows.append((path.stat().st_size, path))
    file_sizes.write_text(
        "".join(f"{size}\t{path}\n" for size, path in sorted(rows, reverse=True)),
        encoding="utf-8",
    )
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")

    sums = HANDOFF / "SHA256SUMS"
    lines: list[str] = []
    for path in sorted(HANDOFF.rglob("*")):
        if path.is_file() and path != sums:
            lines.append(f"{sha256_file(path)}  {path.relative_to(HANDOFF_WT)}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")

    add = run(["git", "-C", str(HANDOFF_WT), "add", "handoff"], timeout=60)
    if add.returncode != 0:
        raise RuntimeError(f"HANDOFF_ADD_FAILED:{add.stderr.strip()}")
    check = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--check"], timeout=60)
    if check.returncode != 0:
        raise RuntimeError(f"HANDOFF_DIFF_CHECK_FAILED:{check.stdout}{check.stderr}")

    diff = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"], timeout=30)
    if diff.returncode not in (0, 1):
        raise RuntimeError(f"HANDOFF_DIFF_FAILED:{diff.stderr.strip()}")
    if diff.returncode == 1:
        commit = run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 4D Darts no-torch smoke {RUN_ID}",
            ],
            timeout=120,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED:{commit.stderr.strip()}")

    push = run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=180)
    if push.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED:{push.stderr.strip()}")
    fetch = run(["git", "-C", str(HANDOFF_WT), "fetch", "origin", BRANCH], timeout=120)
    if fetch.returncode != 0:
        raise RuntimeError(f"HANDOFF_FETCH_FAILED:{fetch.stderr.strip()}")
    local = git_output(["rev-parse", "HEAD"])
    remote = git_output(["rev-parse", f"origin/{BRANCH}"])
    if local != remote:
        raise RuntimeError("HANDOFF_REMOTE_VERIFY_FAILED")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "PHASE4D_DARTS_NOTORCH_CPU_LIFECYCLE",
        "run_id": RUN_ID,
        "source_sha": EXPECTED_SOURCE_SHA,
        "environment": ENV_NAME,
        "status": "FAILED",
        "formal_runtime_certification": False,
        "accuracy_ranking": False,
    }
    try:
        source_gate()
        handoff_sync()
        lane = prerequisite_gate()
        if not PROVIDER.exists():
            raise RuntimeError(f"DARTS_PROVIDER_MISSING:{PROVIDER}")

        runtime = runtime_probe()
        env_contract = environment_contract()
        phase4a_data = phase4a_data_contract()
        data_meta = prepare_smoke_input(phase4a_data)
        dump_json(LOCAL_OUT / "runtime-probe.json", runtime)
        dump_json(LOCAL_OUT / "environment-contract.json", env_contract)
        dump_json(LOCAL_OUT / "data-evidence.json", data_meta)

        public_name, discovery_row = discover_model(data_meta)
        dump_json(
            LOCAL_OUT / "selected-model.json",
            {
                "public_name": public_name,
                "discovery": discovery_row,
                "preferred_order": PREFERRED_MODELS,
            },
        )

        execution = fit_predict_smoke(public_name, data_meta)
        validation = validate_result(execution, data_meta)
        response = execution["response"]
        summary.update(
            {
                "status": validation["status"],
                "formal_runtime_certification": validation["status"] == "VERIFIED",
                "lane": lane,
                "runtime_probe": runtime,
                "environment_contract": env_contract,
                "data": data_meta,
                "model_public_name": public_name,
                "discovery_row": discovery_row,
                "execution": {
                    "returncode": execution["returncode"],
                    "duration_seconds": execution["duration_seconds"],
                    "provider_root_pid": execution["provider_root_pid"],
                    "matched_gpu_pids": execution["matched_gpu_pids"],
                    "gpu_sample_count": execution["gpu_sample_count"],
                    "cuda_visible_devices_for_provider": execution["cuda_visible_devices_for_provider"],
                },
                "response_status": response.get("status"),
                "failure_class": response.get("failure_class"),
                "metrics": response.get("metrics"),
                "baseline_metrics": response.get("baseline_metrics"),
                "validation": validation,
                "device_policy": {
                    "runtime": "notorch",
                    "requested_device": "cpu",
                    "cuda_visible_devices_for_provider": "",
                    "gpu_execution_claimed": False,
                    "cpu_fallback": False,
                },
            }
        )
    except Exception as exc:
        summary["status"] = "FAILED"
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)

    dump_json(LOCAL_OUT / "summary.json", summary)
    write_local_report(summary)
    local_manifest()

    if summary.get("status") != "VERIFIED":
        print("=" * 60)
        print("PHASE4D_DARTS_NOTORCH_SMOKE=FAILED")
        print(f"SUMMARY={LOCAL_OUT / 'summary.json'}")
        print(f"REPORT={LOCAL_OUT / 'PHASE4D_REPORT.md'}")
        if summary.get("error"):
            print(f"ERROR={summary.get('error_type')}: {summary.get('error')}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 60)
        return 20

    head = publish(summary)
    print("=" * 60)
    print("PHASE4D_DARTS_NOTORCH_SMOKE=VERIFIED")
    print(f"HANDOFF_HEAD={head}")
    print(f"SUMMARY={HANDOFF_OUT / 'summary.json'}")
    print(f"REPORT={HANDOFF_OUT / 'PHASE4D_REPORT.md'}")
    print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 4D結果を確認して次へ進めてください")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
