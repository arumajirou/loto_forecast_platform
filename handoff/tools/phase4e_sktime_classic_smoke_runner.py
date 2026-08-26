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
from collections import Counter
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
ENV_NAME = "environments/sktime-classic-py312"
RUNTIME = ROOT / ENV_NAME / ".venv/bin/python"
ENV_PROJECT = SOURCE_WT / ENV_NAME
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase4e-sktime-classic-smoke-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase4e"
MODEL_DIR = LOCAL_OUT / "models"
CHILD = LOCAL_OUT / "sktime-classic-child.py"

MODEL_PUBLIC_NAME = "NaiveForecaster"
MODEL_STRATEGY = "drift"
EXPECTED_SKTIME = "1.0.1"
EXPECTED_PYTHON_PREFIX = "3.12."
BASELINES = (
    "random",
    "fixed",
    "mean",
    "median",
    "last",
    "frequency",
    "seasonal_naive",
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
    head = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"])
    if head.returncode != 0 or head.stdout.strip() != EXPECTED_SOURCE_SHA:
        raise RuntimeError("SOURCE_SHA_GATE_FAILED")
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
    phase4d_path = HANDOFF / "phase4d/summary.json"
    if not phase4d_path.exists():
        raise RuntimeError("PHASE4D_SUMMARY_MISSING")
    phase4d = json.loads(phase4d_path.read_text("utf-8"))
    if phase4d.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4D_NOT_VERIFIED")

    phase3d = json.loads((HANDOFF / "phase3d/summary.json").read_text("utf-8"))
    if phase3d.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError("PHASE3D_SOURCE_SHA_MISMATCH")
    ready = read_tsv(HANDOFF / "phase3d/phase4-ready-queue.tsv")
    row = next((item for item in ready if item.get("environment") == ENV_NAME), None)
    if row is None:
        raise RuntimeError("SKTIME_CLASSIC_NOT_IN_PHASE4_READY_QUEUE")
    if row.get("phase4_smoke_allowed") != "True":
        raise RuntimeError("SKTIME_CLASSIC_PHASE4_SMOKE_NOT_ALLOWED")
    if row.get("lane") != "CURRENT_CPU_LEGACY":
        raise RuntimeError(f"SKTIME_CLASSIC_UNEXPECTED_LANE:{row.get('lane')}")
    return row


def runtime_probe() -> dict[str, Any]:
    if not RUNTIME.exists() or not os.access(RUNTIME, os.X_OK):
        raise RuntimeError(f"SKTIME_CLASSIC_RUNTIME_MISSING:{RUNTIME}")
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

from sktime.forecasting.naive import NaiveForecaster

payload = {
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "sktime": version("sktime"),
    "numpy": version("numpy"),
    "pandas": version("pandas"),
    "statsmodels": version("statsmodels"),
    "torch_installed": importlib.util.find_spec("torch") is not None,
    "naive_forecaster_module": NaiveForecaster.__module__,
    "naive_forecaster_class": NaiveForecaster.__name__,
}
print(json.dumps(payload, sort_keys=True))
'''
    proc = run([str(RUNTIME), "-I", "-c", code], timeout=60)
    (LOCAL_OUT / "runtime-probe.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "runtime-probe.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"SKTIME_CLASSIC_RUNTIME_PROBE_FAILED:{proc.stderr.strip()}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if payload.get("sktime") != EXPECTED_SKTIME:
        raise RuntimeError(f"SKTIME_VERSION_MISMATCH:{payload.get('sktime')}")
    if not str(payload.get("python", "")).startswith(EXPECTED_PYTHON_PREFIX):
        raise RuntimeError(f"SKTIME_PYTHON_MISMATCH:{payload.get('python')}")
    if not str(payload.get("prefix", "")).endswith(f"/{ENV_NAME}/.venv"):
        raise RuntimeError(f"SKTIME_PREFIX_MISMATCH:{payload.get('prefix')}")
    if payload.get("naive_forecaster_class") != MODEL_PUBLIC_NAME:
        raise RuntimeError("SKTIME_NAIVE_FORECASTER_IMPORT_MISMATCH")
    return payload


def environment_contract() -> dict[str, Any]:
    pyproject = ENV_PROJECT / "pyproject.toml"
    if not pyproject.exists():
        raise RuntimeError(f"SKTIME_CLASSIC_PYPROJECT_MISSING:{pyproject}")
    text = pyproject.read_text("utf-8")
    required = (
        'requires-python = ">=3.12,<3.13"',
        '"sktime==1.0.1"',
        '"numpy>=2.0,<2.4"',
        '"pandas>=2.2,<2.4"',
    )
    if not all(token in text for token in required):
        raise RuntimeError("SKTIME_CLASSIC_PYPROJECT_CONTRACT_MISMATCH")
    lock = ENV_PROJECT / "uv.lock"
    return {
        "pyproject_path": str(pyproject),
        "pyproject_sha256": sha256_file(pyproject),
        "uv_lock_exists": lock.exists(),
        "uv_lock_sha256": sha256_file(lock) if lock.exists() else None,
        "dependencies_modified": False,
        "lockfile_modified": False,
    }


def phase4a_data_contract() -> dict[str, Any]:
    phase4a = json.loads((HANDOFF / "phase4a/summary.json").read_text("utf-8"))
    if phase4a.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4A_DATA_CONTRACT_NOT_VERIFIED")
    data = dict(phase4a.get("data") or {})
    source = Path(str(data.get("source_path", "")))
    if not source.is_file():
        raise RuntimeError(f"PHASE4A_REAL_DATA_SOURCE_MISSING:{source}")
    expected_hash = str(data.get("source_sha256", ""))
    actual_hash = sha256_file(source)
    if not expected_hash or actual_hash != expected_hash:
        raise RuntimeError(
            f"PHASE4A_REAL_DATA_HASH_MISMATCH:expected={expected_hash}:actual={actual_hash}"
        )
    positions = list(data.get("position_columns") or [])
    if positions != ["n1", "n2", "n3", "n4"]:
        raise RuntimeError(f"PHASE4A_POSITION_CONTRACT_MISMATCH:{positions}")
    if int(data.get("rows", 0)) != 128:
        raise RuntimeError(f"PHASE4A_ROW_CONTRACT_MISMATCH:{data.get('rows')}")
    return data


def write_child() -> None:
    CHILD.write_text(
        r'''#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sktime.forecasting.naive import NaiveForecaster


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate(actual, predicted, tolerance=1.0):
    y_true = np.asarray(actual, dtype=float)
    y_pred = np.asarray(predicted, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError(f"shape mismatch: actual={y_true.shape}, predicted={y_pred.shape}")
    if not np.isfinite(y_true).all() or not np.isfinite(y_pred).all():
        raise ValueError("metrics input contains NaN or Inf")
    errors = y_pred - y_true
    absolute = np.abs(errors)
    squared = np.square(errors)
    hits = absolute <= tolerance
    return {
        "hit_at_plus_minus_1": float(hits.mean()),
        "position_hit_at_plus_minus_1": [float(v) for v in hits.mean(axis=1)],
        "all_position_hit_at_plus_minus_1": float(hits.all(axis=0).mean()),
        "mae": float(absolute.mean()),
        "mse": float(squared.mean()),
        "rmse": float(np.sqrt(squared.mean())),
        "positions": int(y_true.shape[0]),
        "horizon": int(y_true.shape[1]),
        "tolerance": float(tolerance),
    }


def frequency_value(values):
    counts = Counter(float(v) for v in values)
    highest = max(counts.values())
    return min(value for value, count in counts.items() if count == highest)


def baseline_values(train, positions, min_value, max_value, seed=1):
    matrix = train[positions].to_numpy(dtype=float).T
    horizon = 1
    fixed = float((min_value + max_value) / 2.0)
    rng = np.random.default_rng(seed)
    return {
        "random": rng.integers(min_value, max_value + 1, size=(len(positions), horizon)).astype(float),
        "fixed": np.full((len(positions), horizon), fixed, dtype=float),
        "mean": np.repeat(matrix.mean(axis=1, keepdims=True), horizon, axis=1),
        "median": np.repeat(np.median(matrix, axis=1, keepdims=True), horizon, axis=1),
        "last": np.repeat(matrix[:, -1:], horizon, axis=1),
        "frequency": np.asarray([frequency_value(row) for row in matrix], dtype=float)[:, None],
        "seasonal_naive": np.repeat(matrix[:, -1:], horizon, axis=1),
    }


def prepare(source: Path, output: Path, meta_path: Path, expected_positions: list[str], draw_col: str):
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    else:
        frame = pd.read_parquet(source)
    required = [draw_col, *expected_positions]
    frame = frame[required].copy()
    frame[draw_col] = pd.to_numeric(frame[draw_col], errors="coerce")
    for col in expected_positions:
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
    if len(contiguous) < 128:
        raise RuntimeError(f"contiguous rows too short: {len(contiguous)}")
    contiguous = contiguous.tail(128).copy()
    output.parent.mkdir(parents=True, exist_ok=True)
    contiguous.to_csv(output, index=False)
    values = contiguous[expected_positions].to_numpy(dtype=float)
    payload = {
        "process_id": os.getpid(),
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "derived_path": str(output),
        "derived_sha256": sha256_file(output),
        "draw_no_col": draw_col,
        "position_columns": expected_positions,
        "rows": int(len(contiguous)),
        "first_draw": int(contiguous[draw_col].iloc[0]),
        "last_draw": int(contiguous[draw_col].iloc[-1]),
        "min_value": int(math.floor(float(values.min()))),
        "max_value": int(math.ceil(float(values.max()))),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "sktime": importlib.metadata.version("sktime"),
    }
    dump(meta_path, payload)


def fit(data_path: Path, model_dir: Path, result_path: Path, positions: list[str], min_value: int, max_value: int):
    frame = pd.read_csv(data_path)
    train = frame.iloc[:-1].copy(deep=True)
    actual = frame.iloc[-1:][positions].to_numpy(dtype=float).T
    predictions = []
    models = []
    model_dir.mkdir(parents=True, exist_ok=True)
    for index, col in enumerate(positions, start=1):
        y = train[col].astype(float).reset_index(drop=True)
        model = NaiveForecaster(strategy="drift")
        model.fit(y)
        pred = np.asarray(model.predict(fh=[1]), dtype=float).reshape(-1)
        if pred.shape != (1,) or not np.isfinite(pred).all():
            raise RuntimeError(f"invalid prediction for {col}: shape={pred.shape} values={pred}")
        artifact = model_dir / f"position-{index}.pickle"
        with artifact.open("wb") as handle:
            pickle.dump(model, handle, protocol=pickle.HIGHEST_PROTOCOL)
        predictions.append([float(pred[0])])
        models.append({
            "position": col,
            "model_class": type(model).__name__,
            "strategy": model.strategy,
            "prediction": [float(pred[0])],
            "prediction_shape": [1],
            "prediction_finite": True,
            "artifact_path": str(artifact),
            "artifact_sha256": sha256_file(artifact),
            "native_save_available": callable(getattr(model, "save", None)),
        })
    predicted = np.asarray(predictions, dtype=float)
    metrics = evaluate(actual, predicted)
    baseline_metrics = {
        name: evaluate(actual, values)
        for name, values in baseline_values(train, positions, min_value, max_value, seed=1).items()
    }
    payload = {
        "status": "VERIFIED",
        "operation": "FIT_PREDICT_SERIALIZE",
        "process_id": os.getpid(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "torch_imported": "torch" in sys.modules,
        "sktime": importlib.metadata.version("sktime"),
        "model_public_name": "NaiveForecaster",
        "strategy": "drift",
        "positions": positions,
        "training_rows": int(len(train)),
        "holdout_rows": 1,
        "predictions": predictions,
        "actual": actual.tolist(),
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "models": models,
    }
    dump(result_path, payload)


def load_predict(model_dir: Path, result_path: Path, positions: list[str]):
    rows = []
    predictions = []
    for index, col in enumerate(positions, start=1):
        artifact = model_dir / f"position-{index}.pickle"
        before_hash = sha256_file(artifact)
        with artifact.open("rb") as handle:
            model = pickle.load(handle)
        pred = np.asarray(model.predict(fh=[1]), dtype=float).reshape(-1)
        if pred.shape != (1,) or not np.isfinite(pred).all():
            raise RuntimeError(f"invalid reloaded prediction for {col}: shape={pred.shape} values={pred}")
        after_hash = sha256_file(artifact)
        if before_hash != after_hash:
            raise RuntimeError(f"artifact changed while loading: {artifact}")
        predictions.append([float(pred[0])])
        rows.append({
            "position": col,
            "model_class": type(model).__name__,
            "strategy": getattr(model, "strategy", None),
            "prediction": [float(pred[0])],
            "prediction_shape": [1],
            "prediction_finite": True,
            "artifact_path": str(artifact),
            "artifact_sha256": after_hash,
        })
    dump(result_path, {
        "status": "VERIFIED",
        "operation": "SEPARATE_PROCESS_RELOAD_PREDICT",
        "process_id": os.getpid(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "torch_imported": "torch" in sys.modules,
        "sktime": importlib.metadata.version("sktime"),
        "predictions": predictions,
        "models": rows,
    })


def main():
    op = sys.argv[1]
    if op == "prepare":
        prepare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5].split(","), sys.argv[6])
    elif op == "fit":
        fit(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5].split(","), int(sys.argv[6]), int(sys.argv[7]))
    elif op == "load":
        load_predict(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4].split(","))
    else:
        raise SystemExit(f"unsupported operation: {op}")


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )


def cpu_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    return env


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
        parts = [part.strip() for part in line.split(",", 2)]
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


def descendants(root_pid: int) -> set[int]:
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


def monitored_child(
    args: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
    timeout: int = 600,
) -> dict[str, Any]:
    env = cpu_env()
    started = time.time()
    samples: list[dict[str, Any]] = []
    matched: set[int] = set()
    peak = 0
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            [str(RUNTIME), str(CHILD), *args],
            stdout=out,
            stderr=err,
            text=True,
            env=env,
        )
        while proc.poll() is None:
            elapsed = time.time() - started
            if elapsed > timeout:
                proc.kill()
                proc.wait(timeout=10)
                raise RuntimeError(f"SKTIME_CHILD_TIMEOUT:{args[0]}:{timeout}")
            pids = descendants(proc.pid)
            gpu_rows = gpu_process_rows()
            matching = [row for row in gpu_rows if row["pid"] in pids]
            for row in matching:
                matched.add(row["pid"])
                peak = max(peak, row["used_memory_mib"])
            samples.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": args[0],
                    "root_pid": proc.pid,
                    "descendants": sorted(pids),
                    "matching_gpu_processes": matching,
                }
            )
            time.sleep(0.05)
        rc = proc.wait(timeout=10)
    return {
        "returncode": rc,
        "root_pid": proc.pid,
        "duration_seconds": time.time() - started,
        "matched_gpu_pids": sorted(matched),
        "peak_matching_gpu_memory_mib": peak,
        "samples": samples,
    }


def prepare_data(data: dict[str, Any]) -> dict[str, Any]:
    output = LOCAL_OUT / "smoke-input.csv"
    meta = LOCAL_OUT / "data-evidence.json"
    proc = run(
        [
            str(RUNTIME),
            str(CHILD),
            "prepare",
            str(data["source_path"]),
            str(output),
            str(meta),
            ",".join(data["position_columns"]),
            str(data["draw_no_col"]),
        ],
        timeout=180,
        env=cpu_env(),
    )
    (LOCAL_OUT / "prepare.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "prepare.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0 or not meta.exists():
        raise RuntimeError(f"SKTIME_DATA_PREPARE_FAILED:{proc.stderr.strip()}")
    observed = json.loads(meta.read_text("utf-8"))
    identity_keys = (
        "source_sha256",
        "derived_sha256",
        "draw_no_col",
        "position_columns",
        "rows",
        "first_draw",
        "last_draw",
        "min_value",
        "max_value",
    )
    for key in identity_keys:
        expected = data.get(key)
        actual = observed.get(key)
        if expected != actual:
            raise RuntimeError(f"SKTIME_DATA_IDENTITY_MISMATCH:{key}:expected={expected}:actual={actual}")
    if observed.get("cuda_visible_devices") != "":
        raise RuntimeError("SKTIME_DATA_PREPARE_CPU_ENV_NOT_PINNED")
    return observed


def execute_lifecycle(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fit_result = LOCAL_OUT / "fit-result.json"
    load_result = LOCAL_OUT / "reload-result.json"
    positions_csv = ",".join(data["position_columns"])
    fit_monitor = monitored_child(
        [
            "fit",
            str(LOCAL_OUT / "smoke-input.csv"),
            str(MODEL_DIR),
            str(fit_result),
            positions_csv,
            str(data["min_value"]),
            str(data["max_value"]),
        ],
        stdout_path=LOCAL_OUT / "fit.stdout.log",
        stderr_path=LOCAL_OUT / "fit.stderr.log",
        timeout=600,
    )
    if fit_monitor["returncode"] != 0 or not fit_result.exists():
        stderr = (LOCAL_OUT / "fit.stderr.log").read_text("utf-8", errors="replace")
        raise RuntimeError(f"SKTIME_FIT_PROCESS_FAILED:rc={fit_monitor['returncode']}:{stderr[-2000:]}")

    reload_monitor = monitored_child(
        ["load", str(MODEL_DIR), str(load_result), positions_csv],
        stdout_path=LOCAL_OUT / "reload.stdout.log",
        stderr_path=LOCAL_OUT / "reload.stderr.log",
        timeout=300,
    )
    if reload_monitor["returncode"] != 0 or not load_result.exists():
        stderr = (LOCAL_OUT / "reload.stderr.log").read_text("utf-8", errors="replace")
        raise RuntimeError(f"SKTIME_RELOAD_PROCESS_FAILED:rc={reload_monitor['returncode']}:{stderr[-2000:]}")

    all_samples = fit_monitor.pop("samples") + reload_monitor.pop("samples")
    with (LOCAL_OUT / "gpu-process-samples.jsonl").open("w", encoding="utf-8") as handle:
        for row in all_samples:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return (
        json.loads(fit_result.read_text("utf-8")),
        json.loads(load_result.read_text("utf-8")),
        {"fit": fit_monitor, "reload": reload_monitor},
    )


def metric_keys_complete(metrics: dict[str, Any]) -> bool:
    return {
        "hit_at_plus_minus_1",
        "position_hit_at_plus_minus_1",
        "all_position_hit_at_plus_minus_1",
        "mae",
        "mse",
        "rmse",
    }.issubset(metrics)


def validate_lifecycle(
    fit: dict[str, Any],
    reload: dict[str, Any],
    monitors: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    fit_predictions = fit.get("predictions") or []
    reload_predictions = reload.get("predictions") or []
    expected_positions = list(data["position_columns"])
    fit_pid = fit.get("process_id")
    reload_pid = reload.get("process_id")

    prediction_equal = False
    if len(fit_predictions) == len(reload_predictions) == len(expected_positions):
        try:
            prediction_equal = all(
                len(a) == len(b) == 1
                and math.isfinite(float(a[0]))
                and math.isfinite(float(b[0]))
                and math.isclose(float(a[0]), float(b[0]), rel_tol=1e-12, abs_tol=1e-12)
                for a, b in zip(fit_predictions, reload_predictions, strict=True)
            )
        except Exception:
            prediction_equal = False

    fit_models = fit.get("models") or []
    reload_models = reload.get("models") or []
    metrics = fit.get("metrics") or {}
    baseline_metrics = fit.get("baseline_metrics") or {}

    checks = {
        "fit_status_verified": fit.get("status") == "VERIFIED",
        "reload_status_verified": reload.get("status") == "VERIFIED",
        "sktime_version_fit": fit.get("sktime") == EXPECTED_SKTIME,
        "sktime_version_reload": reload.get("sktime") == EXPECTED_SKTIME,
        "model_identity_fit": fit.get("model_public_name") == MODEL_PUBLIC_NAME,
        "strategy_fit": fit.get("strategy") == MODEL_STRATEGY,
        "four_positions_fit": len(fit_models) == 4,
        "four_positions_reload": len(reload_models) == 4,
        "fit_shape_finite_all": bool(fit_models)
        and all(row.get("prediction_shape") == [1] and row.get("prediction_finite") is True for row in fit_models),
        "reload_shape_finite_all": bool(reload_models)
        and all(row.get("prediction_shape") == [1] and row.get("prediction_finite") is True for row in reload_models),
        "separate_process_reload": bool(fit_pid and reload_pid and int(fit_pid) != int(reload_pid)),
        "prediction_equal_after_reload": prediction_equal,
        "cpu_env_fit": fit.get("cuda_visible_devices") == "",
        "cpu_env_reload": reload.get("cuda_visible_devices") == "",
        "torch_not_imported_fit": fit.get("torch_imported") is False,
        "torch_not_imported_reload": reload.get("torch_imported") is False,
        "no_gpu_pid_fit": not monitors["fit"].get("matched_gpu_pids"),
        "no_gpu_pid_reload": not monitors["reload"].get("matched_gpu_pids"),
        "metrics_complete": metric_keys_complete(metrics),
        "baselines_complete": set(baseline_metrics) == set(BASELINES)
        and all(metric_keys_complete(value) for value in baseline_metrics.values()),
        "training_holdout_ordered": fit.get("training_rows") == 127 and fit.get("holdout_rows") == 1,
    }
    checks["all_critical_checks_pass"] = all(checks.values())
    return {
        "checks": checks,
        "fit_process_id": fit_pid,
        "reload_process_id": reload_pid,
        "fit_predictions": fit_predictions,
        "reload_predictions": reload_predictions,
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "model_artifacts": [
            {
                "position": row.get("position"),
                "model_class": row.get("model_class"),
                "strategy": row.get("strategy"),
                "artifact_sha256": row.get("artifact_sha256"),
                "native_save_available": row.get("native_save_available"),
            }
            for row in fit_models
        ],
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
    sums = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            sums.append(f"{sha256_file(path)}  {path}")
    (LOCAL_OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")


def publish(summary: dict[str, Any]) -> str:
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("REFUSE_TO_PUBLISH_NON_VERIFIED_PHASE4E")
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    HANDOFF_OUT.mkdir(parents=True, exist_ok=True)

    allowed_suffixes = {".json", ".jsonl", ".md", ".log", ".txt", ".tsv"}
    for src in sorted(LOCAL_OUT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(LOCAL_OUT)
        if "models" in rel.parts or rel.name == "smoke-input.csv" or rel == Path("sktime-classic-child.py"):
            continue
        if src.suffix.lower() not in allowed_suffixes and src.name not in {"SHA256SUMS"}:
            continue
        dst = HANDOFF_OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    report = HANDOFF_OUT / "PHASE4E_REPORT.md"
    validation = summary["validation"]
    runtime = summary["runtime"]
    report.write_text(
        "\n".join(
            [
                "# Phase 4E — sktime classic Python 3.12 CPU runtime smoke",
                "",
                f"- status: **{summary['status']}**",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                f"- environment: `{ENV_NAME}`",
                f"- runtime: `{RUNTIME}`",
                f"- Python: `{runtime.get('python')}`",
                f"- sktime: `{runtime.get('sktime')}`",
                f"- model: `{MODEL_PUBLIC_NAME}(strategy={MODEL_STRATEGY!r})`",
                "- execution contract: **CPU intended** (`CUDA_VISIBLE_DEVICES` empty)",
                "- GPU model execution: **NOT CLAIMED**",
                "- lifecycle: FIT → PREDICT → Python pickle → separate-process RELOAD → PREDICT",
                f"- fit PID: `{validation.get('fit_process_id')}`",
                f"- reload PID: `{validation.get('reload_process_id')}`",
                "- data: exact Phase 4A verified 128-row real-data window",
                "- evaluation: 127 train rows + final 1-row holdout",
                "- ranking: **non-ranking runtime smoke**; formal multi-seed/time-split ranking remains Phase 6",
                "",
                "## Critical checks",
                "",
                *[f"- {key}: `{value}`" for key, value in validation["checks"].items()],
                "",
                "## Runtime-smoke metrics",
                "",
                f"- Hit@±1: `{validation['metrics'].get('hit_at_plus_minus_1')}`",
                f"- MAE: `{validation['metrics'].get('mae')}`",
                f"- MSE: `{validation['metrics'].get('mse')}`",
                f"- RMSE: `{validation['metrics'].get('rmse')}`",
                f"- position Hit@±1: `{validation['metrics'].get('position_hit_at_plus_minus_1')}`",
                f"- all-position Hit@±1: `{validation['metrics'].get('all_position_hit_at_plus_minus_1')}`",
                "",
                "## Interpretation",
                "",
                "This phase certifies the existing sktime 1.0.1 classic Python 3.12 runtime without dependency or lockfile mutation. Metrics and baselines are retained only as smoke evidence and must not be promoted as Phase 6 ranking evidence.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text("utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff.setdefault("completed_phases", {})["phase4e"] = "VERIFIED"
    handoff["current_phase"] = "phase4e_sktime_classic_verified_phase4f_next"
    handoff["phase4e"] = summary
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    progress = handoff.get("estimated_progress_percent", "unknown")
    progress_line = f"- estimated progress: `{progress}%`" if isinstance(progress, (int, float)) else f"- estimated progress: `{progress}`"
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
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 4E",
                "",
                f"- runtime: `{RUNTIME}`",
                f"- Python: `{runtime.get('python')}`",
                f"- sktime: `{runtime.get('sktime')}`",
                f"- model: `{MODEL_PUBLIC_NAME}` / strategy `{MODEL_STRATEGY}`",
                "- runtime contract: `classic CPU`",
                "- CUDA hidden from model processes: `True`",
                f"- model-process GPU PIDs: `{summary['gpu']['matched_gpu_pids']}`",
                f"- separate-process reload: `{validation['checks']['separate_process_reload']}`",
                f"- prediction equality after reload: `{validation['checks']['prediction_equal_after_reload']}`",
                "- dependency/lock mutation: `False`",
                "- accuracy ranking: `False` (Phase 6 remains pending)",
                "",
                "## Next",
                "",
                "Continue with `environments/sktime-core-py313`, then `environments/statsforecast-py313`, and finally `environments/toto2-4m-py312` from the Phase 4 ready queue.",
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
    added = "\n".join(line for line in diff.stdout.splitlines() if line.startswith("+") and not line.startswith("+++"))
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
                f"audit: publish Phase 4E sktime classic smoke {RUN_ID}",
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
        raise RuntimeError(f"HANDOFF_REMOTE_VERIFY_FAILED:local={local}:remote={remote}")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "PHASE4E_SKTIME_CLASSIC_PY312_CPU_LIFECYCLE",
        "run_id": RUN_ID,
        "source_sha": EXPECTED_SOURCE_SHA,
        "environment": ENV_NAME,
        "status": "FAILED",
        "formal_runtime_certification": False,
        "scope": "sktime classic Python 3.12 CPU real-data lifecycle smoke",
        "dataset_policy": {
            "kind": "exact_phase4a_verified_real_data_window",
            "accuracy_ranking": False,
            "phase6_metrics_pending": [
                "Hit@±1",
                "MAE",
                "MSE",
                "RMSE",
                "position_Hit@±1",
                "all_position_Hit@±1",
            ],
        },
        "device_policy": {
            "requested": "cpu",
            "cuda_visible_devices": "",
            "gpu_execution_claimed": False,
            "cpu_fallback": False,
            "reason": "CPU is the intended Phase 4E classic-runtime contract",
        },
    }
    try:
        source_gate()
        handoff_sync()
        lane = prerequisite_gate()
        runtime = runtime_probe()
        env_contract = environment_contract()
        phase4a_data = phase4a_data_contract()
        write_child()
        prepared_data = prepare_data(phase4a_data)
        fit, reload, monitors = execute_lifecycle(prepared_data)
        validation = validate_lifecycle(fit, reload, monitors, prepared_data)
        status = "VERIFIED" if validation["checks"]["all_critical_checks_pass"] else "FAILED"
        matched_gpu = sorted(
            set(monitors["fit"].get("matched_gpu_pids", []))
            | set(monitors["reload"].get("matched_gpu_pids", []))
        )
        summary.update(
            {
                "status": status,
                "formal_runtime_certification": status == "VERIFIED",
                "lane": lane,
                "runtime": runtime,
                "environment_contract": env_contract,
                "data": prepared_data,
                "model": {
                    "public_name": MODEL_PUBLIC_NAME,
                    "strategy": MODEL_STRATEGY,
                    "serialization": "python-pickle",
                    "separate_process_reload": True,
                },
                "gpu": {
                    "matched_gpu_pids": matched_gpu,
                    "fit_monitor": monitors["fit"],
                    "reload_monitor": monitors["reload"],
                },
                "validation": validation,
                "metrics": validation["metrics"],
                "baseline_metrics": validation["baseline_metrics"],
                "dependencies_modified": False,
                "lockfile_modified": False,
            }
        )
        if status != "VERIFIED":
            raise RuntimeError("PHASE4E_CRITICAL_VALIDATION_FAILED")
    except Exception as exc:
        summary["status"] = "FAILED"
        summary["formal_runtime_certification"] = False
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)

    dump_json(LOCAL_OUT / "summary.json", summary)
    report = LOCAL_OUT / "PHASE4E_REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# Phase 4E sktime classic CPU smoke — local execution",
                "",
                f"- status: `{summary['status']}`",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                f"- runtime: `{RUNTIME}`",
                f"- model: `{MODEL_PUBLIC_NAME}` / `{MODEL_STRATEGY}`",
                f"- error: `{summary.get('error', '')}`",
                "",
                "This local report is non-ranking runtime certification evidence. Phase 6 remains the formal accuracy comparison phase.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    local_manifest()

    if summary["status"] != "VERIFIED":
        print("=" * 60)
        print("PHASE4E_SKTIME_CLASSIC_SMOKE=FAILED")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print(f"LOCAL_SUMMARY={LOCAL_OUT / 'summary.json'}")
        print(f"LOCAL_REPORT={LOCAL_OUT / 'PHASE4E_REPORT.md'}")
        print(f"ERROR={summary.get('error_type')}:{summary.get('error')}")
        print("=" * 60)
        return 2

    head = publish(summary)
    print("=" * 60)
    print("PHASE4E_SKTIME_CLASSIC_SMOKE=VERIFIED")
    print(f"HANDOFF_HEAD={head}")
    print(f"SUMMARY={HANDOFF_OUT / 'summary.json'}")
    print(f"REPORT={HANDOFF_OUT / 'PHASE4E_REPORT.md'}")
    print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 4E結果を確認して次へ進めてください")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
