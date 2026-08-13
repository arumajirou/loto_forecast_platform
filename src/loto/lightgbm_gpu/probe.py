from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np


def candidate_device_types(requested: str) -> tuple[str, ...]:
    """Return the ordered LightGBM accelerator backends to probe."""
    if requested == "auto":
        return ("cuda", "gpu")
    if requested in {"cuda", "gpu"}:
        return (requested,)
    raise ValueError(f"unsupported device type: {requested}")


def gpu_activity_evidence(
    *,
    baseline_memory_mib: float,
    max_memory_mib: float,
    max_util_percent: float,
    min_memory_delta_mib: float,
) -> bool:
    """Require external evidence that the attempted backend exercised the NVIDIA GPU."""
    memory_delta = max_memory_mib - baseline_memory_mib
    return max_util_percent > 0.0 or memory_delta >= min_memory_delta_mib


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nvidia_snapshot() -> dict[str, Any] | None:
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,"
        "utilization.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first = proc.stdout.splitlines()[0]
    parts = [item.strip() for item in first.split(",")]
    if len(parts) < 7:
        return None
    try:
        return {
            "name": parts[0],
            "driver_version": parts[1],
            "memory_total_mib": float(parts[2]),
            "memory_used_mib": float(parts[3]),
            "memory_free_mib": float(parts[4]),
            "utilization_percent": float(parts[5]),
            "power_w": float(parts[6]),
        }
    except ValueError:
        return None


def _telemetry_worker(path: Path, stop: threading.Event, interval: float) -> None:
    query = [
        "nvidia-smi",
        "--query-gpu=timestamp,utilization.gpu,memory.used,memory.free,power.draw",
        "--format=csv,noheader,nounits",
    ]
    with path.open("a", encoding="utf-8") as stream:
        while not stop.is_set():
            try:
                proc = subprocess.run(
                    query,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                proc = None
            if proc is not None and proc.returncode == 0 and proc.stdout.strip():
                stream.write(proc.stdout.splitlines()[0].strip() + "\n")
                stream.flush()
            stop.wait(interval)


def _telemetry_summary(path: Path, baseline_memory_mib: float) -> dict[str, Any]:
    max_util = 0.0
    max_memory = baseline_memory_mib
    max_power = 0.0
    samples = 0
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            reader = csv.reader(stream)
            for row in reader:
                if len(row) < 5:
                    continue
                try:
                    util = float(row[1].strip())
                    memory = float(row[2].strip())
                    power = float(row[4].strip())
                except ValueError:
                    continue
                samples += 1
                max_util = max(max_util, util)
                max_memory = max(max_memory, memory)
                max_power = max(max_power, power)
    return {
        "samples": samples,
        "baseline_memory_mib": baseline_memory_mib,
        "max_memory_mib": max_memory,
        "memory_delta_mib": max_memory - baseline_memory_mib,
        "max_util_percent": max_util,
        "max_power_w": max_power,
    }


def _synthetic_data(rows: int, features: int, seed: int) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(rows, features)).astype(np.float32)
    weights = rng.normal(size=features).astype(np.float32)
    signal = x @ weights
    classifier_y = (signal > np.median(signal)).astype(np.int32)
    regressor_y = (signal + rng.normal(scale=0.25, size=rows)).astype(np.float32)
    return x, classifier_y, regressor_y


def _fit_lightgbm(
    *,
    device_type: str,
    rows: int,
    features: int,
    rounds: int,
    seed: int,
) -> dict[str, Any]:
    import lightgbm as lgb

    x, classifier_y, regressor_y = _synthetic_data(rows, features, seed)
    common = {
        "n_estimators": rounds,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "max_bin": 63,
        "verbosity": -1,
        "random_state": seed,
        "device_type": device_type,
        "n_jobs": 4,
    }

    started = time.perf_counter()
    classifier = lgb.LGBMClassifier(**common)
    classifier.fit(x, classifier_y)
    classifier_elapsed = time.perf_counter() - started
    classifier_pred = np.asarray(classifier.predict_proba(x[:128]), dtype=float)
    if not np.isfinite(classifier_pred).all():
        raise RuntimeError("classifier predictions contain non-finite values")

    started = time.perf_counter()
    regressor = lgb.LGBMRegressor(**common)
    regressor.fit(x, regressor_y)
    regressor_elapsed = time.perf_counter() - started
    regressor_pred = np.asarray(regressor.predict(x[:128]), dtype=float)
    if not np.isfinite(regressor_pred).all():
        raise RuntimeError("regressor predictions contain non-finite values")

    return {
        "lightgbm_version": getattr(lgb, "__version__", "UNKNOWN"),
        "lightgbm_module": getattr(lgb, "__file__", None),
        "classifier_elapsed_seconds": classifier_elapsed,
        "regressor_elapsed_seconds": regressor_elapsed,
        "classifier_prediction_shape": list(classifier_pred.shape),
        "regressor_prediction_shape": list(regressor_pred.shape),
        "classifier_finite": True,
        "regressor_finite": True,
    }


def run_probe(
    *,
    output: Path,
    requested_device_type: str,
    rows: int,
    features: int,
    rounds: int,
    seed: int,
    telemetry_interval: float,
    min_memory_delta_mib: float,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)

    gpu = _nvidia_snapshot()
    base_payload: dict[str, Any] = {
        "schema_version": 1,
        "requested_device_type": requested_device_type,
        "python": sys.version,
        "platform": platform.platform(),
        "seed": seed,
        "rows": rows,
        "features": features,
        "rounds": rounds,
        "gpu": gpu,
        "attempts": [],
        "selected_device_type": None,
        "status": "BLOCKED_NO_NVIDIA_GPU" if gpu is None else "NOT_RUN",
    }
    if gpu is None:
        _atomic_json(output / "CERTIFICATION.json", base_payload)
        return base_payload

    baseline_memory_mib = float(gpu["memory_used_mib"])
    attempts: list[dict[str, Any]] = []
    selected: str | None = None

    for device_type in candidate_device_types(requested_device_type):
        telemetry_path = output / f"telemetry-{device_type}.csv"
        stop = threading.Event()
        thread = threading.Thread(
            target=_telemetry_worker,
            args=(telemetry_path, stop, telemetry_interval),
            daemon=True,
        )
        thread.start()
        attempt_started = time.perf_counter()
        fit_result: dict[str, Any] | None = None
        error_type: str | None = None
        error: str | None = None
        try:
            fit_result = _fit_lightgbm(
                device_type=device_type,
                rows=rows,
                features=features,
                rounds=rounds,
                seed=seed,
            )
        except Exception as exc:  # fail-visible capability probe
            error_type = type(exc).__name__
            error = str(exc)
        finally:
            stop.set()
            thread.join(timeout=5)

        telemetry = _telemetry_summary(telemetry_path, baseline_memory_mib)
        activity = gpu_activity_evidence(
            baseline_memory_mib=baseline_memory_mib,
            max_memory_mib=float(telemetry["max_memory_mib"]),
            max_util_percent=float(telemetry["max_util_percent"]),
            min_memory_delta_mib=min_memory_delta_mib,
        )
        if fit_result is not None and activity:
            status = "VERIFIED"
            selected = device_type
        elif fit_result is not None:
            status = "INCONCLUSIVE_NO_EXTERNAL_GPU_ACTIVITY"
        else:
            status = "UNSUPPORTED_OR_FAILED"

        attempts.append(
            {
                "device_type": device_type,
                "status": status,
                "elapsed_seconds": time.perf_counter() - attempt_started,
                "fit": fit_result,
                "telemetry": telemetry,
                "gpu_activity_evidence": activity,
                "error_type": error_type,
                "error": error,
            }
        )
        if selected is not None:
            break

    if selected is not None:
        overall = "VERIFIED"
    elif any(item["status"] == "INCONCLUSIVE_NO_EXTERNAL_GPU_ACTIVITY" for item in attempts):
        overall = "INCONCLUSIVE"
    else:
        overall = "UNSUPPORTED_BUILD_OR_RUNTIME"

    payload = base_payload | {
        "attempts": attempts,
        "selected_device_type": selected,
        "status": overall,
    }
    certification = output / "CERTIFICATION.json"
    _atomic_json(certification, payload)

    checksum_targets = [certification, *sorted(output.glob("telemetry-*.csv"))]
    checksum_lines = [f"{_sha256(path)}  {path.name}" for path in checksum_targets]
    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Certify installed LightGBM GPU/CUDA capability")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device-type", choices=("auto", "cuda", "gpu"), default="auto")
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--features", type=int, default=64)
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--telemetry-interval", type=float, default=0.10)
    parser.add_argument("--min-memory-delta-mib", type=float, default=32.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_probe(
        output=Path(args.output),
        requested_device_type=args.device_type,
        rows=args.rows,
        features=args.features,
        rounds=args.rounds,
        seed=args.seed,
        telemetry_interval=args.telemetry_interval,
        min_memory_delta_mib=args.min_memory_delta_mib,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    status = payload["status"]
    if status == "VERIFIED":
        print("LIGHTGBM_GPU_BUILD_CERTIFICATION=VERIFIED")
        return 0
    if status == "BLOCKED_NO_NVIDIA_GPU":
        print("LIGHTGBM_GPU_BUILD_CERTIFICATION=BLOCKED_NO_NVIDIA_GPU")
        return 2
    if status == "INCONCLUSIVE":
        print("LIGHTGBM_GPU_BUILD_CERTIFICATION=INCONCLUSIVE")
        return 4
    print("LIGHTGBM_GPU_BUILD_CERTIFICATION=UNSUPPORTED_BUILD_OR_RUNTIME")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
