#!/usr/bin/env python
# ruff: noqa: E402,E501
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

AUTOGLUON_ENV = ROOT / "environments" / "autogluon-timeseries"
AUTOGLUON_RUNNER = ROOT / "scripts" / "run_autogluon_timeseries_provider.py"
WORKER_SUBPROCESS_LIBRARIES = {"autogluon"}

from loto.data.canonical import canonicalize_loto7
from loto.data.lineage import atomic_write_json
from loto.models.argument_verifier import verify_arguments
from loto.models.artifact_store import load_pickle_model, model_manifest, save_pickle_model
from loto.models.catalog import ModelSpec, list_model_specs
from loto.models.lifecycle import ModelLifecycleResult, candidate_metrics, run_candidate_lifecycle, validate_prediction
from loto.models.property_inspector import inspect_model_properties
from loto.models.providers import FoundationProviderError, get_foundation_provider
from loto.models.workers import PositionSeriesWorker, normalize_worker_predictions
from loto.observability.gpu import collect_gpu_evidence
from loto.orchestration.resource_scheduler import ResourcePolicy, ResourceScheduler


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real lifecycle validation for catalog models.")
    parser.add_argument("--catalog", default="configs/model_catalog.json")
    parser.add_argument("--catalog-source", choices=["static", "dynamic", "merged"], default="static")
    parser.add_argument("--available-only", action="store_true")
    parser.add_argument("--models", default="all", help="'all' or comma separated model IDs")
    parser.add_argument("--data", default="examples/sample_loto7.csv")
    parser.add_argument("--require-fit", action="store_true")
    parser.add_argument("--require-predict", action="store_true")
    parser.add_argument("--require-save", action="store_true")
    parser.add_argument("--require-load", action="store_true")
    parser.add_argument("--require-retrain", action="store_true")
    parser.add_argument("--require-property-validation", action="store_true")
    parser.add_argument("--verify-arguments", action="store_true")
    parser.add_argument("--verify-gpu", action="store_true")
    parser.add_argument("--parallel-cpu-models", type=positive_int, default=4)
    parser.add_argument("--parallel-gpu-models", type=non_negative_int, default=1)
    parser.add_argument("--cpus-per-trial", type=positive_int, default=1)
    parser.add_argument("--gpus-per-trial", type=non_negative_int, default=0)
    parser.add_argument("--max-vram-mib", type=positive_int, default=14500)
    parser.add_argument("--gpu-memory-safety-margin-mib", type=non_negative_int, default=1024)
    parser.add_argument("--timeout", type=positive_int, default=1800)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", default="runs/all-model-runtime-validation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--precision", default="32")
    return parser


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def spec_catalog_sha256(specs: list[ModelSpec]) -> str:
    payload = [spec.to_dict() for spec in specs]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def extract_status_rows(data: object) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise TypeError(f"status payload must be list or dict, got {type(data).__name__}")
    for key in ("rows", "models", "results", "model_results"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    raise ValueError("No model status rows found in supported keys")


def load_static_specs(catalog_path: Path, *, available_only: bool) -> list[ModelSpec]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    rows = extract_status_rows(data)
    specs = [
        ModelSpec(
            model_id=str(row["model_id"]),
            family=str(row["family"]),
            library=str(row["library"]),
            task=str(row["task"]),
            class_name=str(row["class_name"]),
            priority=str(row.get("priority", "p1")),
            package=row.get("package"),
            capabilities=tuple(row.get("capabilities", ())),
            default_params=dict(row.get("default_params", {})),
            notes=str(row.get("notes", "")),
        )
        for row in rows
    ]
    if available_only:
        specs = [spec for spec in specs if spec.available]
    return specs


def resolve_specs(args: argparse.Namespace, catalog_path: Path) -> tuple[list[ModelSpec], dict[str, Any]]:
    static_specs: list[ModelSpec] = []
    static_sha = file_sha256(catalog_path)
    if args.catalog_source in {"static", "merged"}:
        if not catalog_path.exists():
            raise SystemExit(f"catalog does not exist: {catalog_path}")
        static_specs = load_static_specs(catalog_path, available_only=args.available_only)

    dynamic_specs = list_model_specs(available_only=args.available_only)
    if args.catalog_source == "static":
        specs = static_specs
        override_count = 0
    elif args.catalog_source == "dynamic":
        specs = dynamic_specs
        override_count = 0
    else:
        by_id = {spec.model_id: spec for spec in dynamic_specs}
        override_count = 0
        for spec in static_specs:
            if spec.model_id in by_id:
                override_count += 1
            by_id[spec.model_id] = spec
        dynamic_order = [spec.model_id for spec in dynamic_specs]
        static_only = [spec.model_id for spec in static_specs if spec.model_id not in dynamic_order]
        specs = [by_id[model_id] for model_id in dynamic_order + static_only]

    if args.models != "all":
        requested = [item.strip() for item in args.models.split(",") if item.strip()]
        known = {spec.model_id: spec for spec in specs}
        missing = [model_id for model_id in requested if model_id not in known]
        if missing:
            raise SystemExit(f"unknown or unavailable model(s): {', '.join(missing)}")
        specs = [known[model_id] for model_id in requested]

    catalog_sha = spec_catalog_sha256(specs)
    info = {
        "catalog_source": args.catalog_source,
        "catalog_path": str(catalog_path) if args.catalog_source in {"static", "merged"} else None,
        "catalog_count": len(specs),
        "catalog_sha256": catalog_sha,
        "static_catalog_sha256": static_sha,
        "dynamic_catalog_version": spec_catalog_sha256(dynamic_specs),
        "dynamic_catalog_count": len(dynamic_specs),
        "override_count": override_count,
    }
    return specs, info


def select_specs(models: str, *, available_only: bool):
    specs = list_model_specs(available_only=available_only)
    if models == "all":
        return specs
    requested = [item.strip() for item in models.split(",") if item.strip()]
    known = {spec.model_id: spec for spec in specs}
    missing = [model_id for model_id in requested if model_id not in known]
    if missing:
        raise SystemExit(f"unknown or unavailable model(s): {', '.join(missing)}")
    return [known[model_id] for model_id in requested]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_prediction_artifact(path: Path, values: np.ndarray) -> None:
    frame = pd.DataFrame({"index": np.arange(len(values)), "prediction": np.asarray(values, dtype=float)})
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except Exception:
        frame.to_csv(path.with_suffix(".csv"), index=False)


def args_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    return {key: getattr(args, key) for key in sorted(vars(args))}


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def dependency_report() -> dict[str, Any]:
    packages = [
        "numpy",
        "pandas",
        "scikit-learn",
        "lightgbm",
        "statsforecast",
        "mlforecast",
        "neuralforecast",
        "torch",
        "transformers",
        "chronos",
        "huggingface_hub",
        "safetensors",
        "accelerate",
        "timesfm",
        "tirex",
        "uni2ts",
    ]
    result: dict[str, Any] = {}
    for package in packages:
        try:
            result[package] = {"status": "INSTALLED", "version": importlib.metadata.version(package)}
        except importlib.metadata.PackageNotFoundError:
            result[package] = {"status": "MISSING", "version": None}
    return result


def environment_report() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
        "gpu": collect_gpu_evidence(gpu_required=False),
    }


def nvidia_smi_text() -> str:
    try:
        proc = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10, check=False)
    except Exception as exc:
        return f"nvidia-smi failed: {type(exc).__name__}: {exc}\n"
    return proc.stdout + proc.stderr


def write_yaml_like(path: Path, payload: dict[str, Any]) -> None:
    lines = []
    for key, value in payload.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, default=str)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_candidate_probabilities(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    validate_prediction(arr, expected_shape=(37,))
    return {
        "probability_min": float(arr.min()),
        "probability_max": float(arr.max()),
        "probability_sum": float(arr.sum()),
        "top7": (np.argsort(-arr)[:7] + 1).astype(int).tolist(),
        "range_status": "OK" if np.all((arr >= 0.0) & (arr <= 1.0)) else "OUT_OF_RANGE",
    }


def prediction_stage_metrics(
    *,
    predictions: np.ndarray,
    reloaded_predictions: np.ndarray | None,
    retrained_predictions: np.ndarray | None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "initial_prediction_length": int(np.asarray(predictions).size),
        "reload_prediction_length": None
        if reloaded_predictions is None
        else int(np.asarray(reloaded_predictions).size),
        "retrain_prediction_length": None
        if retrained_predictions is None
        else int(np.asarray(retrained_predictions).size),
    }
    if reloaded_predictions is not None and predictions.size and reloaded_predictions.size:
        metrics["prediction_parity_max_abs_diff"] = float(
            np.max(np.abs(predictions - reloaded_predictions))
        )
    return metrics


def write_trial_artifacts(
    trial_dir: Path,
    spec,
    result: ModelLifecycleResult,
    *,
    requested: dict[str, Any],
    effective: dict[str, Any],
    config: dict[str, Any],
    trial_events: list[dict[str, Any]],
) -> None:
    trial_dir.mkdir(parents=True, exist_ok=True)
    write_yaml_like(trial_dir / "resolved_config.yaml", config)
    atomic_write_json(trial_dir / "requested_arguments.json", requested)
    atomic_write_json(trial_dir / "effective_arguments.json", effective)
    atomic_write_json(trial_dir / "argument_verification.json", result.argument_evidence)
    atomic_write_json(trial_dir / "properties_before.json", result.properties_before)
    atomic_write_json(trial_dir / "properties_after_fit.json", result.properties_after_fit)
    atomic_write_json(trial_dir / "properties_after_load.json", result.properties_after_load)
    atomic_write_json(trial_dir / "properties_after_retrain.json", result.properties_after_retrain)
    metrics = dict(result.metrics)
    metrics.update(
        prediction_stage_metrics(
            predictions=result.predictions,
            reloaded_predictions=result.reloaded_predictions,
            retrained_predictions=result.retrained_predictions,
        )
    )
    if result.predictions.size == 37:
        metrics.update(validate_candidate_probabilities(result.predictions))
    atomic_write_json(trial_dir / "metrics.json", metrics)
    atomic_write_json(trial_dir / "gpu_evidence.json", result.resource_evidence)
    write_jsonl(
        trial_dir / "resource_samples.jsonl",
        [
            {"stage": "before", **result.resource_evidence.get("before", {})},
            {"stage": "after", **result.resource_evidence.get("after", {})},
        ],
    )
    atomic_write_json(trial_dir / "process_tree.json", {"pid": os.getpid(), "children": []})
    write_jsonl(trial_dir / "events.jsonl", trial_events)
    atomic_write_json(
        trial_dir / "failure.json",
        {"errors": result.errors, "final_status": result.final_status} if result.errors else {},
    )
    if result.model_artifact is None and not (trial_dir / "model_manifest.json").exists():
        atomic_write_json(
            trial_dir / "model_manifest.json",
            {
                "model_id": spec.model_id,
                "library": spec.library,
                "exists": False,
                "load_test_status": result.load_status,
                "prediction_test_status": result.predict_status,
                "status": "ARTIFACT_MISSING",
            },
        )


def neuralforecast_smoke_params(spec, args: argparse.Namespace) -> dict[str, Any]:
    if spec.library == "neuralforecast_auto":
        params = dict(spec.default_params)
        params.update({
            "backend": "optuna",
            "num_samples": 1,
            "max_steps": 1,
            "parallel_trials": 1,
            "refit_with_val": False,
            "search_strategy": "random",
            "input_size": 16,
            "batch_size": 32,
        })
        if spec.class_name in {"AutoNBEATS", "AutoNBEATSx"}:
            params.update({
                "stack_types": ["identity"],
                "n_blocks": [1],
                "mlp_units": [[64, 64]],
            })
        if spec.class_name == "AutoTimesNet":
            params.update({
                "input_size": 16,
                "max_steps": 5,
                "batch_size": 32,
                "hidden_size": 32,
                "conv_hidden_size": 32,
                "top_k": 2,
                "num_kernels": 2,
                "encoder_layers": 1,
            })
        return params
    if spec.library != "neuralforecast":
        return dict(spec.default_params)
    params = dict(spec.default_params)
    params.setdefault("input_size", 16)
    params.setdefault("max_steps", 1)
    params.setdefault("batch_size", 16)
    params.setdefault("learning_rate", 0.001)
    params.setdefault("val_check_steps", 1)
    params.setdefault("early_stop_patience_steps", -1)
    if spec.class_name in {"NBEATS", "NBEATSx"}:
        params.update({
            "stack_types": ["identity"],
            "n_blocks": [1],
            "mlp_units": [[64, 64]],
        })
    if spec.class_name == "TimesNet":
        params.update({
            "input_size": 16,
            "max_steps": 5,
            "batch_size": 32,
            "hidden_size": 32,
            "conv_hidden_size": 32,
            "top_k": 2,
            "num_kernels": 2,
            "encoder_layers": 1,
        })
    return params


def read_prediction_file(path: Path) -> np.ndarray:
    if path.suffix == ".parquet":
        try:
            frame = pd.read_parquet(path)
        except Exception:
            frame = pd.read_csv(path.with_suffix(".csv"))
    else:
        frame = pd.read_csv(path)
    return frame["prediction"].to_numpy(float)


def run_neuralforecast_reload_subprocess(
    *,
    model_dir: Path,
    frame_path: Path,
    output_path: Path,
    value_col: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    code = r"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from neuralforecast import NeuralForecast

model_dir = Path(sys.argv[1])
frame_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
value_col = sys.argv[4]
nf = NeuralForecast.load(str(model_dir), verbose=False)
frame = pd.read_csv(frame_path)
frame["ds"] = pd.to_datetime(frame["ds"])
np.random.seed(42)
pred = nf.predict(df=frame, random_seed=42).reset_index()
col = value_col if value_col in pred.columns else [c for c in pred.columns if c not in {"unique_id", "ds", "index"}][0]
values = pred.sort_values("unique_id")[col].to_numpy(float)
pd.DataFrame({"index": np.arange(len(values)), "prediction": values}).to_parquet(output_path, index=False)
print(json.dumps({"column": col, "shape": list(values.shape), "finite": bool(np.isfinite(values).all())}))
"""
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-c", code, str(model_dir), str(frame_path), str(output_path), value_col],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "elapsed_seconds": time.time() - started,
        "output_path": str(output_path),
    }
    if proc.returncode == 0 and output_path.exists():
        result["prediction_shape"] = list(read_prediction_file(output_path).shape)
    return result


def run_autohint_reload_subprocess(
    *,
    model_path: Path,
    frame_path: Path,
    output_path: Path,
    value_col: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    code = r"""
import json
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd

model_path = Path(sys.argv[1])
frame_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
value_col = sys.argv[4]
with model_path.open("rb") as stream:
    payload = pickle.load(stream)
nf = payload["neuralforecast"]
frame = pd.read_csv(frame_path)
frame["ds"] = pd.to_datetime(frame["ds"])
np.random.seed(42)
pred = nf.predict(df=frame, random_seed=42).reset_index()
col = value_col if value_col in pred.columns else [c for c in pred.columns if c not in {"unique_id", "ds", "index"}][0]
bottom_order = payload["hierarchy"].get(
    "internal_bottom_series_order",
    payload["hierarchy"]["bottom_series_order"],
)
values = pred.set_index("unique_id").loc[bottom_order, col].to_numpy(float)
pd.DataFrame({"index": np.arange(len(values)), "prediction": values}).to_parquet(output_path, index=False)
total_id = payload["hierarchy"].get("internal_series_order", ["total"])[0]
total = float(pred.set_index("unique_id").loc[total_id, col])
print(json.dumps({
    "column": col,
    "shape": list(values.shape),
    "finite": bool(np.isfinite(values).all()),
    "coherence_error": abs(total - float(values.sum())),
}))
"""
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-c", code, str(model_path), str(frame_path), str(output_path), value_col],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "elapsed_seconds": time.time() - started,
        "output_path": str(output_path),
    }
    if proc.returncode == 0 and output_path.exists():
        result["prediction_shape"] = list(read_prediction_file(output_path).shape)
    return result


def write_autohint_hierarchy_artifacts(trial_dir: Path, hierarchy: dict[str, Any]) -> None:
    atomic_write_json(trial_dir / "hierarchy_definition.json", hierarchy["hierarchy_definition"])
    np.save(trial_dir / "summation_matrix.npy", hierarchy["summation_matrix"])
    atomic_write_json(
        trial_dir / "summation_matrix_sha256.json",
        {"sha256": hierarchy["summation_matrix_sha256"]},
    )
    atomic_write_json(trial_dir / "series_order.json", hierarchy["series_order"])
    atomic_write_json(trial_dir / "bottom_series_order.json", hierarchy["bottom_series_order"])
    atomic_write_json(trial_dir / "hierarchy_validation.json", hierarchy["hierarchy_validation"])


def run_foundation_reload_subprocess(
    *,
    model_id: str,
    artifact_dir: Path,
    data_path: str,
    output_path: Path,
    device: str,
    precision: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    code = r"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.data.canonical import canonicalize_loto7
from loto.models.catalog import get_model_spec
from loto.models.providers import get_foundation_provider

model_id = sys.argv[2]
artifact_dir = Path(sys.argv[3])
data_path = sys.argv[4]
output_path = Path(sys.argv[5])
device = sys.argv[6]
precision = sys.argv[7]

spec = get_model_spec(model_id)
raw = pd.read_csv(data_path)
master, _ = canonicalize_loto7(raw, source=data_path)
provider = get_foundation_provider(spec)(spec, dict(spec.default_params), seed=42, device=device, precision=precision)
try:
    provider.load_saved(artifact_dir)
    values = np.asarray(provider.predict(master.iloc[:-1].copy()), dtype=float).reshape(7)
    pd.DataFrame({"index": np.arange(len(values)), "prediction": values}).to_parquet(output_path, index=False)
    print(json.dumps({"shape": list(values.shape), "finite": bool(np.isfinite(values).all())}))
finally:
    provider.close()
"""
    started = time.time()
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(ROOT),
            model_id,
            str(artifact_dir),
            data_path,
            str(output_path),
            device,
            precision,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "elapsed_seconds": time.time() - started,
        "output_path": str(output_path),
    }
    if proc.returncode == 0 and output_path.exists():
        result["prediction_shape"] = list(read_prediction_file(output_path).shape)
    return result


FOUNDATION_CANDIDATE_LIBRARIES = {"tabpfn_time_series"}


def run_foundation_candidate_reload_subprocess(
    *,
    model_id: str,
    artifact_dir: Path,
    data_path: str,
    output_path: Path,
    device: str,
    precision: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    code = r"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.data.canonical import canonicalize_loto7
from loto.models.catalog import get_model_spec
from loto.models.providers import get_foundation_provider
from loto.models.workers import normalize_worker_predictions

model_id = sys.argv[2]
artifact_dir = Path(sys.argv[3])
data_path = sys.argv[4]
output_path = Path(sys.argv[5])
device = sys.argv[6]
precision = sys.argv[7]

spec = get_model_spec(model_id)
raw = pd.read_csv(data_path)
master, _ = canonicalize_loto7(raw, source=data_path)
history = master.iloc[:-1].copy()
provider = get_foundation_provider(spec)(spec, dict(spec.default_params), seed=42, device=device, precision=precision)
try:
    provider.load_saved(artifact_dir)
    raw_values = np.asarray(provider.predict(history), dtype=float).reshape(37)
    values = normalize_worker_predictions(task="candidate", history=history, values=raw_values)
    pd.DataFrame({"index": np.arange(len(values)), "prediction": values}).to_parquet(output_path, index=False)
    print(json.dumps({"shape": list(values.shape), "finite": bool(np.isfinite(values).all())}))
finally:
    provider.close()
"""
    started = time.time()
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(ROOT),
            model_id,
            str(artifact_dir),
            data_path,
            str(output_path),
            device,
            precision,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "elapsed_seconds": time.time() - started,
        "output_path": str(output_path),
    }
    if proc.returncode == 0 and output_path.exists():
        result["prediction_shape"] = list(read_prediction_file(output_path).shape)
    return result


def run_autogluon_reload_subprocess(
    *,
    request: dict[str, Any],
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    request_path = output_dir / "autogluon_reload_request.json"
    response_path = output_dir / "autogluon_reload_response.json"
    atomic_write_json(request_path, request)
    started = time.time()
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(AUTOGLUON_ENV),
            "python",
            str(AUTOGLUON_RUNNER),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "elapsed_seconds": time.time() - started,
    }
    if proc.returncode != 0:
        result["status"] = "ERROR"
        result["message"] = f"AutoGluon-TimeSeries reload subprocess failed rc={proc.returncode}"
        return result
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["status"] = "ERROR"
        result["message"] = f"AutoGluon-TimeSeries reload subprocess returned invalid JSON: {exc}"
        return result
    result.update(response)
    return result


def unsupported_result(spec, output_dir: Path, status: str, reason: str) -> ModelLifecycleResult:
    props = inspect_model_properties(spec, None, params=spec.default_params)
    result = ModelLifecycleResult(
        model_id=spec.model_id,
        fit_status="NOT_RUN",
        predict_status="NOT_RUN",
        save_status="NOT_RUN",
        load_status="NOT_RUN",
        retrain_status="NOT_RUN",
        model_artifact=None,
        predictions=np.asarray([], dtype=float),
        reloaded_predictions=None,
        retrained_predictions=None,
        properties_before=props,
        properties_after_fit={},
        properties_after_load={},
        properties_after_retrain={},
        argument_evidence=[],
        resource_evidence={"gpu": collect_gpu_evidence(gpu_required=False)},
        errors=[{"stage": "dispatch", "type": status, "message": reason}],
        final_status=status,
    )
    atomic_write_json(output_dir / "lifecycle_result.json", result.to_dict())
    return result


def run_foundation_lifecycle(spec, master: pd.DataFrame, args, output_dir: Path) -> ModelLifecycleResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    effective_device = "cuda" if args.verify_gpu else args.device
    requested = dict(spec.default_params) | {
        "seed": args.seed,
        "device": effective_device,
        "precision": args.precision,
        "local_files_only": True,
    }
    before = inspect_model_properties(spec, None, params=requested, device=effective_device, precision=args.precision)
    gpu_required = args.verify_gpu and ("gpu" in spec.capabilities or "gpu_optional" in spec.capabilities or "zero_shot" in spec.capabilities)
    resource_before = collect_gpu_evidence(gpu_required=gpu_required)
    provider = get_foundation_provider(spec)(spec, dict(spec.default_params), seed=args.seed, device=effective_device, precision=args.precision)
    errors: list[dict[str, Any]] = []
    predictions = np.asarray([], dtype=float)
    reloaded_predictions = None
    model_artifact: Path | None = None
    fit_status = "UNSUPPORTED_OPERATION"
    predict_status = "NOT_RUN"
    save_status = "NOT_RUN"
    load_status = "NOT_RUN"
    retrain_status = "UNSUPPORTED_OPERATION"
    final_status = "PROVIDER_NOT_IMPLEMENTED"
    properties_after_fit: dict[str, Any] = {}
    properties_after_load: dict[str, Any] = {}
    properties_after_retrain: dict[str, Any] = {}
    try:
        provider.load()
        values = np.asarray(provider.predict(master.iloc[:-1].copy()), dtype=float).reshape(7)
        validate_prediction(values, expected_shape=(7,))
        predictions = values
        predict_status = "OK"
        properties_after_fit = provider.inspect_properties()
        model_artifact = provider.save(output_dir / "models" / "foundation")
        save_status = "OK"
        reload_path = output_dir / "reloaded_predictions.parquet"
        reload_result = run_foundation_reload_subprocess(
            model_id=spec.model_id,
            artifact_dir=model_artifact,
            data_path=args.data,
            output_path=reload_path,
            device=effective_device,
            precision=args.precision,
            timeout_seconds=args.timeout,
        )
        atomic_write_json(output_dir / "subprocess_reload.json", reload_result)
        if reload_result["returncode"] != 0:
            raise FoundationProviderError(
                "RELOADED_PREDICT_FAILED",
                f"foundation subprocess reload failed: {reload_result['stderr'] or reload_result['stdout']}",
            )
        reloaded_predictions = read_prediction_file(reload_path)
        validate_prediction(reloaded_predictions, expected_shape=(7,))
        max_abs_diff = float(np.max(np.abs(predictions - reloaded_predictions)))
        if max_abs_diff > 1e-5:
            raise FoundationProviderError("PREDICTION_MISMATCH", f"max_abs_diff={max_abs_diff}")
        load_status = "OK"
        properties_after_load = provider.inspect_properties()
        properties_after_retrain = provider.inspect_properties() | {"retrain_supported": False}
        final_status = "ZERO_SHOT_PASS"
        atomic_write_json(
            output_dir / "model_manifest.json",
            model_manifest(
                model_artifact,
                model_id=spec.model_id,
                library=spec.library,
                library_version=before.get("library_version"),
                load_test_status=load_status,
                prediction_test_status=predict_status,
            ),
        )
    except FoundationProviderError as exc:
        final_status = exc.status
        errors.append({"stage": "foundation", "type": exc.status, "message": str(exc)})
    except Exception as exc:
        final_status = "PREDICT_FAILED"
        errors.append({"stage": "foundation", "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        provider.close()
    resource_after = collect_gpu_evidence(gpu_required=gpu_required)
    provider_gpu_evidence = {}
    if hasattr(provider, "last_response"):
        provider_gpu_evidence = dict(getattr(provider, "last_response", {}).get("gpu_evidence", {}) or {})
    if (
        final_status == "ZERO_SHOT_PASS"
        and gpu_required
        and not resource_after.get("eligible", False)
        and provider_gpu_evidence.get("gpu_used") is True
        and int(provider_gpu_evidence.get("peak_vram_bytes") or 0) > 0
    ):
        resource_after = dict(resource_after)
        resource_after.update({
            "eligible": True,
            "reasons": ["subprocess_gpu_evidence"],
            "model_device": provider_gpu_evidence.get("execution_device", "cuda"),
            "batch_device": provider_gpu_evidence.get("execution_device", "cuda"),
            "vram_peak_bytes": int(provider_gpu_evidence.get("peak_vram_bytes") or 0),
            "subprocess_gpu_evidence": provider_gpu_evidence,
        })
    if final_status == "ZERO_SHOT_PASS" and gpu_required and not resource_after.get("eligible", False):
        final_status = "GPU_PARTIAL"
        errors.append({"stage": "gpu_evidence", "type": "GPU_PARTIAL", "message": ";".join(resource_after.get("reasons", []))})
    result = ModelLifecycleResult(
        model_id=spec.model_id,
        fit_status=fit_status,
        predict_status=predict_status,
        save_status=save_status,
        load_status=load_status,
        retrain_status=retrain_status,
        model_artifact=model_artifact,
        predictions=predictions,
        reloaded_predictions=reloaded_predictions,
        retrained_predictions=None,
        properties_before=before,
        properties_after_fit=properties_after_fit,
        properties_after_load=properties_after_load,
        properties_after_retrain=properties_after_retrain,
        argument_evidence=verify_arguments(requested, requested, properties_after_fit or before),
        resource_evidence={"before": resource_before, "after": resource_after, "provider": provider_gpu_evidence},
        errors=errors,
        final_status=final_status,
        metrics={"prediction_count": int(predictions.size)},
    )
    atomic_write_json(output_dir / "lifecycle_result.json", result.to_dict())
    return result


def run_foundation_candidate_lifecycle(spec, master: pd.DataFrame, args, output_dir: Path) -> ModelLifecycleResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    effective_device = "cuda" if args.verify_gpu else args.device
    requested = dict(spec.default_params) | {
        "seed": args.seed,
        "device": effective_device,
        "precision": args.precision,
        "local_files_only": True,
    }
    before = inspect_model_properties(spec, None, params=requested, device=effective_device, precision=args.precision)
    gpu_required = args.verify_gpu and ("gpu" in spec.capabilities or "gpu_optional" in spec.capabilities or "zero_shot" in spec.capabilities)
    resource_before = collect_gpu_evidence(gpu_required=gpu_required)
    provider = get_foundation_provider(spec)(spec, dict(spec.default_params), seed=args.seed, device=effective_device, precision=args.precision)
    errors: list[dict[str, Any]] = []
    predictions = np.asarray([], dtype=float)
    reloaded_predictions = None
    model_artifact: Path | None = None
    fit_status = "UNSUPPORTED_OPERATION"
    predict_status = "NOT_RUN"
    save_status = "NOT_RUN"
    load_status = "NOT_RUN"
    retrain_status = "UNSUPPORTED_OPERATION"
    final_status = "PROVIDER_NOT_IMPLEMENTED"
    properties_after_fit: dict[str, Any] = {}
    properties_after_load: dict[str, Any] = {}
    properties_after_retrain: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    history = master.iloc[:-1].copy()
    actual_numbers = [int(master.iloc[-1][f"n{i}"]) for i in range(1, 8)]
    try:
        provider.load()
        started = time.time()
        raw_values = np.asarray(provider.predict(history), dtype=float).reshape(37)
        values = normalize_worker_predictions(task="candidate", history=history, values=raw_values)
        elapsed_seconds = time.time() - started
        validate_prediction(values, expected_shape=(37,))
        predictions = values
        predict_status = "OK"
        metrics = candidate_metrics(actual_numbers, predictions, elapsed_seconds=elapsed_seconds)
        properties_after_fit = provider.inspect_properties()
        model_artifact = provider.save(output_dir / "models" / "foundation")
        save_status = "OK"
        reload_path = output_dir / "reloaded_predictions.parquet"
        reload_result = run_foundation_candidate_reload_subprocess(
            model_id=spec.model_id,
            artifact_dir=model_artifact,
            data_path=args.data,
            output_path=reload_path,
            device=effective_device,
            precision=args.precision,
            timeout_seconds=args.timeout,
        )
        atomic_write_json(output_dir / "subprocess_reload.json", reload_result)
        if reload_result["returncode"] != 0:
            raise FoundationProviderError(
                "RELOADED_PREDICT_FAILED",
                f"foundation subprocess reload failed: {reload_result['stderr'] or reload_result['stdout']}",
            )
        reloaded_predictions = read_prediction_file(reload_path)
        validate_prediction(reloaded_predictions, expected_shape=(37,))
        max_abs_diff = float(np.max(np.abs(predictions - reloaded_predictions)))
        if max_abs_diff > 1e-5:
            raise FoundationProviderError("PREDICTION_MISMATCH", f"max_abs_diff={max_abs_diff}")
        load_status = "OK"
        properties_after_load = provider.inspect_properties()
        properties_after_retrain = provider.inspect_properties() | {"retrain_supported": False}
        final_status = "ZERO_SHOT_PASS"
        atomic_write_json(
            output_dir / "model_manifest.json",
            model_manifest(
                model_artifact,
                model_id=spec.model_id,
                library=spec.library,
                library_version=before.get("library_version"),
                load_test_status=load_status,
                prediction_test_status=predict_status,
            ),
        )
    except FoundationProviderError as exc:
        final_status = exc.status
        errors.append({"stage": "foundation", "type": exc.status, "message": str(exc)})
    except Exception as exc:
        final_status = "PREDICT_FAILED"
        errors.append({"stage": "foundation", "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        provider.close()
    resource_after = collect_gpu_evidence(gpu_required=gpu_required)
    provider_gpu_evidence = {}
    if hasattr(provider, "last_response"):
        provider_gpu_evidence = dict(getattr(provider, "last_response", {}).get("gpu_evidence", {}) or {})
    if (
        final_status == "ZERO_SHOT_PASS"
        and gpu_required
        and not resource_after.get("eligible", False)
        and provider_gpu_evidence.get("gpu_used") is True
        and int(provider_gpu_evidence.get("peak_vram_bytes") or 0) > 0
    ):
        resource_after = dict(resource_after)
        resource_after.update({
            "eligible": True,
            "reasons": ["subprocess_gpu_evidence"],
            "model_device": provider_gpu_evidence.get("execution_device", "cuda"),
            "batch_device": provider_gpu_evidence.get("execution_device", "cuda"),
            "vram_peak_bytes": int(provider_gpu_evidence.get("peak_vram_bytes") or 0),
            "subprocess_gpu_evidence": provider_gpu_evidence,
        })
    if final_status == "ZERO_SHOT_PASS" and gpu_required and not resource_after.get("eligible", False):
        final_status = "GPU_PARTIAL"
        errors.append({"stage": "gpu_evidence", "type": "GPU_PARTIAL", "message": ";".join(resource_after.get("reasons", []))})
    result = ModelLifecycleResult(
        model_id=spec.model_id,
        fit_status=fit_status,
        predict_status=predict_status,
        save_status=save_status,
        load_status=load_status,
        retrain_status=retrain_status,
        model_artifact=model_artifact,
        predictions=predictions,
        reloaded_predictions=reloaded_predictions,
        retrained_predictions=None,
        properties_before=before,
        properties_after_fit=properties_after_fit,
        properties_after_load=properties_after_load,
        properties_after_retrain=properties_after_retrain,
        argument_evidence=verify_arguments(requested, requested, properties_after_fit or before),
        resource_evidence={"before": resource_before, "after": resource_after, "provider": provider_gpu_evidence},
        errors=errors,
        final_status=final_status,
        metrics=metrics or {"prediction_count": int(predictions.size)},
    )
    atomic_write_json(output_dir / "lifecycle_result.json", result.to_dict())
    return result


def run_worker_lifecycle(spec, master: pd.DataFrame, args, output_dir: Path) -> ModelLifecycleResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    params = neuralforecast_smoke_params(spec, args)
    effective_device = (
        "cuda"
        if args.verify_gpu and "gpu" in spec.capabilities and args.gpus_per_trial > 0
        else args.device
    )
    before = inspect_model_properties(
        spec, None, params=params, device=effective_device, precision=args.precision
    )
    gpu_required = args.verify_gpu and "gpu" in spec.capabilities
    (output_dir / "nvidia_smi_before.txt").write_text(nvidia_smi_text(), encoding="utf-8")
    resource_before = collect_gpu_evidence(gpu_required=gpu_required)
    errors: list[dict[str, Any]] = []
    predictions = np.asarray([], dtype=float)
    reloaded_predictions = None
    retrained_predictions = None
    model_artifact = None
    fit_status = "OK" if spec.task in {"position", "position_series", "candidate_series", "foundation"} else "NOT_RUN"
    predict_status = "NOT_RUN"
    save_status = "NOT_AVAILABLE"
    load_status = "NOT_RUN"
    retrain_status = "NOT_RUN"
    final_status = "ARTIFACT_MISSING"
    properties_after_fit: dict[str, Any] = {}
    properties_after_load: dict[str, Any] = {}
    properties_after_retrain: dict[str, Any] = {}
    resource_after_override: dict[str, Any] | None = None
    requested = params | {"seed": args.seed, "device": effective_device, "precision": args.precision}
    try:
        started = time.perf_counter()
        output = PositionSeriesWorker(
            spec,
            params,
            seed=args.seed,
            device=effective_device,
            precision=args.precision,
        ).forecast(master.iloc[:-1].copy())
        (output_dir / "nvidia_smi_during.txt").write_text(nvidia_smi_text(), encoding="utf-8")
        elapsed = time.perf_counter() - started
        prediction_values = (
            output.candidate_probabilities
            if spec.task in {"candidate", "candidate_series"} and output.candidate_probabilities is not None
            else output.position_values
        )
        predictions = normalize_worker_predictions(
            task=spec.task,
            history=master.iloc[:-1].copy(),
            values=prediction_values,
        )
        validate_prediction(predictions, expected_shape=(37,))
        predict_status = "OK"
        properties_after_fit = before | output.metadata | {"prediction_time_seconds": elapsed}
        write_prediction_artifact(output_dir / "predictions.parquet", predictions)
        if output.model_artifact_payload is None:
            final_status = "SAVE_FAILED"
            errors.append({
                "stage": "save",
                "type": "ARTIFACT_MISSING",
                "message": "worker forecast returned predictions but no fitted model/save handle",
            })
        else:
            if output.model_artifact_payload.get("library") == "neuralforecast":
                loaded = output.model_artifact_payload
                nf_dir = output_dir / "models" / "neuralforecast"
                nf = loaded["neuralforecast"]
                frame = loaded["frame"]
                value_col = loaded["value_col"]
                frame_path = output_dir / "neuralforecast_frame.csv"
                frame.to_csv(frame_path, index=False)
                nf.save(str(nf_dir), save_dataset=True, overwrite=True)
                model_artifact = nf_dir
                reload_path = output_dir / "reloaded_predictions.parquet"
                reload_result = run_neuralforecast_reload_subprocess(
                    model_dir=nf_dir,
                    frame_path=frame_path,
                    output_path=reload_path,
                    value_col=value_col,
                    timeout_seconds=args.timeout,
                )
                atomic_write_json(output_dir / "subprocess_reload.json", reload_result)
                if reload_result["returncode"] != 0:
                    raise RuntimeError(
                        "NeuralForecast subprocess reload failed: "
                        f"{reload_result['stderr'] or reload_result['stdout']}"
                    )
                history = master.iloc[:-1].copy()
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=read_prediction_file(reload_path),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                max_abs_diff = float(np.max(np.abs(predictions - reloaded_predictions)))
                parity_tolerance = (
                    1e-4
                    if "probabilistic" in spec.capabilities or "DeepAR" in spec.class_name
                    else 1e-5
                )
                if max_abs_diff > parity_tolerance:
                    final_status = "PREDICTION_MISMATCH"
                    errors.append({
                        "stage": "prediction_parity",
                        "type": "PREDICTION_MISMATCH",
                        "message": f"max_abs_diff={max_abs_diff}; tolerance={parity_tolerance}",
                    })
                properties_after_load = inspect_model_properties(
                    spec,
                    nf.models[0] if getattr(nf, "models", None) else nf,
                    params=requested,
                    artifact_path=nf_dir,
                    device=effective_device,
                    precision=args.precision,
                )
                retrained_output = PositionSeriesWorker(
                    spec,
                    params,
                    seed=args.seed,
                    device=effective_device,
                    precision=args.precision,
                ).forecast(master.copy())
                retrained_values = (
                    retrained_output.candidate_probabilities
                    if spec.task in {"candidate", "candidate_series"}
                    and retrained_output.candidate_probabilities is not None
                    else retrained_output.position_values
                )
                retrained_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=master.copy(),
                    values=retrained_values,
                )
                validate_prediction(retrained_predictions, expected_shape=(37,))
                retrain_status = "OK"
                try:
                    resource_after_override = collect_gpu_evidence(
                        gpu_required=gpu_required,
                        model=nf.models[0] if getattr(nf, "models", None) else None,
                    )
                    resource_after_override["trainer_accelerator"] = loaded["params"].get("accelerator")
                    resource_after_override["trainer_devices"] = loaded["params"].get("devices")
                    if (
                        gpu_required
                        and resource_after_override.get("trainer_accelerator") == "gpu"
                        and int(resource_after_override.get("vram_peak_bytes", 0) or 0) > 0
                        and resource_after_override.get("nvidia_smi_processes")
                    ):
                        resource_after_override["eligible"] = True
                        resource_after_override["reasons"] = [
                            "lightning_gpu_accelerator_vram_and_pid_evidence"
                        ]
                except Exception:
                    resource_after_override = None
                properties_after_retrain = before | retrained_output.metadata | {
                    "retrain_method": "full_refit_on_expanded_data",
                    "retrain_rows": int(len(master)),
                }
                if final_status != "PREDICTION_MISMATCH":
                    final_status = "PASS"
                atomic_write_json(
                    output_dir / "retrain_evidence.json",
                    {
                        "retrain_method": "full_refit_on_expanded_data",
                        "initial_train_rows": int(len(master) - 1),
                        "retrain_rows": int(len(master)),
                    },
                )
                atomic_write_json(
                    output_dir / "model_manifest.json",
                    model_manifest(
                        nf_dir,
                        model_id=spec.model_id,
                        library=spec.library,
                        library_version=before.get("library_version"),
                        load_test_status=load_status,
                        prediction_test_status=predict_status,
                    ),
                )
                save_status = "OK"
            else:
                model_artifact = save_pickle_model(output.model_artifact_payload, output_dir / "model.pkl")
                save_status = "OK"
                loaded = load_pickle_model(model_artifact)
            if loaded.get("library") == "statsforecast":
                prediction = loaded["statsforecast"].predict(h=1)
                value_col = loaded["value_col"]
                history = master.iloc[:-1].copy()
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=prediction.sort_values("unique_id")[value_col].to_numpy(float),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = inspect_model_properties(
                    spec,
                    loaded["statsforecast"],
                    params=requested,
                    artifact_path=model_artifact,
                    device=args.device,
                    precision=args.precision,
                )
            elif loaded.get("library") == "mlforecast":
                prediction = loaded["mlforecast"].predict(1)
                value_col = loaded["value_col"]
                history = master.iloc[:-1].copy()
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=prediction.sort_values("unique_id")[value_col].to_numpy(float),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = inspect_model_properties(
                    spec,
                    loaded["mlforecast"],
                    params=requested,
                    artifact_path=model_artifact,
                    device=args.device,
                    precision=args.precision,
                )
            elif loaded.get("library") == "lag_regression":
                lags = [int(lag) for lag in loaded["lags"]]
                history = master.iloc[:-1].copy()
                values = []
                for index, estimator in enumerate(loaded["estimators"], start=1):
                    series = history[f"n{index}"].astype(float).to_numpy()
                    if estimator is None:
                        values.append(float(loaded["fallback_values"][index - 1]))
                    else:
                        query = np.asarray([[series[-lag] for lag in lags]])
                        values.append(float(estimator.predict(query)[0]))
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=np.asarray(values, dtype=float),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = inspect_model_properties(
                    spec,
                    loaded["estimators"][0],
                    params=requested,
                    artifact_path=model_artifact,
                    device=args.device,
                    precision=args.precision,
                )
            elif loaded.get("library") == "reservoirpy_esn":
                history = master.iloc[:-1].copy()
                values = []
                for index, model in enumerate(loaded["models"], start=1):
                    series = history[f"n{index}"].astype(float).to_numpy()
                    prediction = model.run(series[-1:].reshape(1, 1))
                    values.append(float(np.asarray(prediction).reshape(-1)[-1]))
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=np.asarray(values, dtype=float),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = before | loaded.get("metadata", {}) | {
                    "artifact_path": str(model_artifact),
                    "load_method": "pickle_reservoirpy_esn",
                }
            elif loaded.get("library") == "darts_ensemble":
                values = []
                for model in loaded["models"]:
                    values.append(float(model.predict(1).values()[0, 0]))
                history = master.iloc[:-1].copy()
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=np.asarray(values, dtype=float),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = before | loaded.get("metadata", {}) | {
                    "artifact_path": str(model_artifact),
                    "load_method": "pickle_darts_ensemble",
                }
            elif loaded.get("library") == "gluonts_deepar":
                from gluonts.dataset.common import ListDataset

                dataset = ListDataset(loaded["dataset"], freq="D")
                forecasts = list(loaded["predictor"].predict(dataset))
                values = np.asarray([
                    float(np.asarray(forecast.samples).mean(axis=0)[0])
                    for forecast in forecasts
                ])
                history = master.iloc[:-1].copy()
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=values,
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = before | loaded.get("metadata", {}) | {
                    "artifact_path": str(model_artifact),
                    "load_method": "pickle_gluonts_deepar",
                }
            elif loaded.get("library") == "autohint_fixed":
                write_autohint_hierarchy_artifacts(output_dir, loaded["hierarchy"])
                frame_path = output_dir / "autohint_frame.csv"
                loaded["frame"].to_csv(frame_path, index=False)
                reload_path = output_dir / "reloaded_position_predictions.parquet"
                reload_result = run_autohint_reload_subprocess(
                    model_path=model_artifact,
                    frame_path=frame_path,
                    output_path=reload_path,
                    value_col=loaded["value_col"],
                    timeout_seconds=args.timeout,
                )
                atomic_write_json(output_dir / "subprocess_reload.json", reload_result)
                if reload_result["returncode"] != 0:
                    raise RuntimeError(
                        "AutoHINT subprocess reload failed: "
                        f"{reload_result['stderr'] or reload_result['stdout']}"
                    )
                history = master.iloc[:-1].copy()
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=read_prediction_file(reload_path),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = inspect_model_properties(
                    spec,
                    loaded["neuralforecast"].models[0],
                    params=requested,
                    artifact_path=model_artifact,
                    device=args.device,
                    precision=args.precision,
                ) | loaded["metadata"]
                atomic_write_json(
                    output_dir / "coherence_evidence.json",
                    {
                        "initial_coherence_error": loaded["metadata"].get("coherence_error"),
                        "reload_stdout": reload_result.get("stdout"),
                    },
                )
            elif loaded.get("library") == "autogluon":
                autogluon_dir = output_dir / "models" / "autogluon"
                if autogluon_dir.exists():
                    shutil.rmtree(autogluon_dir)
                autogluon_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(loaded["artifact_dir"], str(autogluon_dir))
                model_artifact = autogluon_dir
                history = master.iloc[:-1].copy()
                payload = history[[f"n{i}" for i in range(1, 8)] + ["draw_date"]].copy()
                payload["draw_date"] = payload["draw_date"].astype(str)
                reload_request = {
                    "schema_version": 1,
                    "model_id": spec.model_id,
                    "mode": "load_predict",
                    "artifact_dir": str(autogluon_dir),
                    "history": payload.to_dict(orient="records"),
                    "prediction_length": 1,
                    "eval_metric": "MAE",
                    "seed": args.seed,
                    "device": args.device if args.device != "auto" else "cpu",
                }
                reload_result = run_autogluon_reload_subprocess(
                    request=reload_request,
                    output_dir=output_dir,
                    timeout_seconds=args.timeout,
                )
                atomic_write_json(output_dir / "subprocess_reload.json", reload_result)
                if reload_result.get("status") != "OK":
                    raise RuntimeError(
                        "AutoGluon-TimeSeries subprocess reload failed: "
                        f"{reload_result.get('message') or reload_result.get('stderr') or reload_result.get('stdout')}"
                    )
                reloaded_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=history,
                    values=np.asarray(reload_result["predictions"], dtype=float),
                )
                validate_prediction(reloaded_predictions, expected_shape=(37,))
                load_status = "OK"
                properties_after_load = before | reload_result.get("properties", {}) | {
                    "artifact_path": str(model_artifact),
                    "load_method": "autogluon_subprocess_reload",
                }
            if loaded.get("library") != "neuralforecast":
                retrained_output = PositionSeriesWorker(
                    spec,
                    params,
                    seed=args.seed,
                    device=effective_device,
                    precision=args.precision,
                ).forecast(master.copy())
                retrained_values = (
                    retrained_output.candidate_probabilities
                    if spec.task in {"candidate", "candidate_series"}
                    and retrained_output.candidate_probabilities is not None
                    else retrained_output.position_values
                )
                retrained_predictions = normalize_worker_predictions(
                    task=spec.task,
                    history=master.copy(),
                    values=retrained_values,
                )
                validate_prediction(retrained_predictions, expected_shape=(37,))
                retrain_status = "OK"
                properties_after_retrain = before | retrained_output.metadata
                if loaded.get("library") == "autogluon":
                    retrain_artifact_dir = retrained_output.model_artifact_payload.get("artifact_dir")
                    if retrain_artifact_dir:
                        shutil.rmtree(retrain_artifact_dir, ignore_errors=True)
                if load_status == "OK":
                    final_status = "PASS"
            atomic_write_json(
                output_dir / "model_manifest.json",
                model_manifest(
                    model_artifact,
                    model_id=spec.model_id,
                    library=spec.library,
                    library_version=before.get("library_version"),
                    load_test_status=load_status,
                    prediction_test_status=predict_status,
                ),
            )
    except Exception as exc:
        message = str(exc)
        status = getattr(exc, "status", None)
        if status:
            final_status = status
        elif "requires provider" in message or "not implemented" in message:
            final_status = "PROVIDER_NOT_IMPLEMENTED" if spec.task == "foundation" else "WORKER_NOT_IMPLEMENTED"
        else:
            final_status = "PREDICT_FAILED"
        errors.append({"stage": "fit_predict", "type": type(exc).__name__, "message": message, "traceback": traceback.format_exc()})
    (output_dir / "nvidia_smi_after.txt").write_text(nvidia_smi_text(), encoding="utf-8")
    resource_after = resource_after_override or collect_gpu_evidence(gpu_required=gpu_required)
    if gpu_required and final_status == "PASS" and not resource_after.get("eligible", False):
        final_status = "GPU_PARTIAL"
        errors.append({
            "stage": "gpu_evidence",
            "type": "GPU_PARTIAL",
            "message": ";".join(resource_after.get("reasons", [])),
        })
    result = ModelLifecycleResult(
        model_id=spec.model_id,
        fit_status=fit_status,
        predict_status=predict_status,
        save_status=save_status,
        load_status=load_status,
        retrain_status=retrain_status,
        model_artifact=model_artifact,
        predictions=predictions,
        reloaded_predictions=reloaded_predictions,
        retrained_predictions=retrained_predictions,
        properties_before=before,
        properties_after_fit=properties_after_fit,
        properties_after_load=properties_after_load,
        properties_after_retrain=properties_after_retrain,
        argument_evidence=verify_arguments(requested, requested, properties_after_fit or before),
        resource_evidence={"before": resource_before, "after": resource_after},
        errors=errors,
        final_status=final_status,
        metrics={"prediction_count": int(predictions.size)},
    )
    atomic_write_json(output_dir / "lifecycle_result.json", result.to_dict())
    return result


def flatten_result(
    spec,
    result: ModelLifecycleResult,
    *,
    run_id: str,
    run_signature: str,
    catalog_info: dict[str, Any],
    data_sha256: str | None,
    code_fingerprint: str,
    required_lifecycle_flags: dict[str, bool],
    device: str,
    precision: str,
) -> dict[str, Any]:
    selected_signature = {
        "model_id": spec.model_id,
        "catalog_sha256": catalog_info["catalog_sha256"],
        "data_sha256": data_sha256,
        "resolved_config_sha256": run_signature,
        "code_fingerprint": code_fingerprint,
        "required_lifecycle_flags": required_lifecycle_flags,
        "device": device,
        "precision": precision,
    }
    return {
        "model_id": spec.model_id,
        "library": spec.library,
        "task": spec.task,
        "available": spec.available,
        "fit": result.fit_status,
        "retrain": result.retrain_status,
        "predict": result.predict_status,
        "save": result.save_status,
        "load": result.load_status,
        "reload_predict": "OK" if result.reloaded_predictions is not None else "NOT_RUN",
        "property_inspection": "OK" if result.properties_before else "FAILED",
        "argument_verification": "OK" if result.argument_evidence else "NOT_RUN",
        "GPU利用": result.resource_evidence.get("after", {}).get("eligible", "NOT_REQUIRED"),
        "parallel対応": any(cap in spec.capabilities for cap in ("auto_hpo", "ray")) or spec.library in {"sklearn", "lightgbm"},
        "学習時間": result.metrics.get("training_time_seconds"),
        "推論時間": result.metrics.get("prediction_time_seconds"),
        "最大RAM": None,
        "最大VRAM": result.resource_evidence.get("after", {}).get("vram_peak_bytes"),
        "artifact path": None if result.model_artifact is None else str(result.model_artifact),
        "final_status": result.final_status,
        "failure_reason": "; ".join(error.get("message", "") for error in result.errors),
        "selected_run_id": run_id,
        "selected_signature": selected_signature,
        "selection_reason": "current_run_success" if result.final_status in {"PASS", "ZERO_SHOT_PASS"} else "current_run_latest_failure",
        "superseded_runs": [],
        "artifact_validation": {
            "artifact_path": None if result.model_artifact is None else str(result.model_artifact),
            "exists": bool(result.model_artifact is not None and result.model_artifact.exists()),
            "save_status": result.save_status,
            "load_status": result.load_status,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    catalog_path = Path(args.catalog)
    specs, catalog_info = resolve_specs(args, catalog_path)
    cli_config = args_snapshot(args)
    data_sha256 = file_sha256(Path(args.data))
    code_fingerprint = stable_hash({
        "script": file_sha256(Path(__file__)),
        "workers": file_sha256(ROOT / "src" / "loto" / "models" / "workers.py"),
    })
    required_lifecycle_flags = {
        "require_fit": args.require_fit,
        "require_predict": args.require_predict,
        "require_save": args.require_save,
        "require_load": args.require_load,
        "require_retrain": args.require_retrain,
        "require_property_validation": args.require_property_validation,
        "verify_arguments": args.verify_arguments,
    }
    run_signature = stable_hash({
        "cli": cli_config,
        "models": [spec.model_id for spec in specs],
        "catalog_sha256": catalog_info["catalog_sha256"],
        "data_sha256": data_sha256,
        "code_fingerprint": code_fingerprint,
        "required_lifecycle_flags": required_lifecycle_flags,
        "device": args.device,
        "precision": args.precision,
    })
    output_base = Path(args.output)
    if args.resume:
        candidates = sorted(
            [path for path in output_base.glob("runtime-*") if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        output_root = candidates[0] if candidates else output_base / f"runtime-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        run_id = output_root.name
    else:
        run_id = f"runtime-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        output_root = output_base / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(args.data)
    master, manifest = canonicalize_loto7(raw, source=args.data)
    policy = ResourcePolicy(
        max_parallel_cpu_models=args.parallel_cpu_models,
        max_parallel_gpu_models=args.parallel_gpu_models,
        cpus_per_trial=args.cpus_per_trial,
        gpus_per_trial=args.gpus_per_trial,
        max_vram_mib=args.max_vram_mib,
        gpu_memory_safety_margin_mib=args.gpu_memory_safety_margin_mib,
        timeout_seconds=args.timeout,
    )
    scheduler = ResourceScheduler(policy)
    rows: list[dict[str, Any]] = []
    property_rows: list[dict[str, Any]] = []
    argument_rows: list[dict[str, Any]] = []
    gpu_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    previous_rows: dict[str, dict[str, Any]] = {}
    previous_results = output_root / "all_model_runtime_validation.json"
    if args.resume and previous_results.exists():
        try:
            previous_rows = {
                str(row["model_id"]): row
                for row in extract_status_rows(
                    json.loads(previous_results.read_text(encoding="utf-8"))
                )
            }
        except Exception:
            previous_rows = {}
    atomic_write_json(
        output_root / "run_manifest.json",
        {
            "run_id": run_id,
            "run_signature": run_signature,
            "selected_signature": run_signature,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "cli": cli_config,
            "catalog": str(catalog_path),
            **catalog_info,
            "data_sha256": data_sha256,
            "code_fingerprint": code_fingerprint,
            "required_lifecycle_flags": required_lifecycle_flags,
            "data": args.data,
        },
    )
    atomic_write_json(output_root / "catalog_snapshot.json", [spec.to_dict() for spec in specs])
    atomic_write_json(output_root / "environment.json", environment_report())
    atomic_write_json(output_root / "dependency_report.json", dependency_report())
    for spec in specs:
        trial_dir = output_root / spec.model_id
        if args.resume and (trial_dir / "lifecycle_result.json").exists():
            row = previous_rows.get(spec.model_id)
            artifact = Path(str(row.get("artifact path"))) if row and row.get("artifact path") else None
            if row and row.get("final_status") == "PASS" and artifact is not None and artifact.exists():
                rows.append(row)
                events.append({"event": "trial_resumed_skip", "model_id": spec.model_id})
                continue
            if row and row.get("final_status") == "PASS" and artifact is None:
                events.append({"event": "trial_resume_rejected", "model_id": spec.model_id, "reason": "missing artifact path"})
            elif row and row.get("final_status") == "PASS":
                events.append({"event": "trial_resume_rejected", "model_id": spec.model_id, "reason": "artifact missing"})
        trial_events: list[dict[str, Any]] = []
        lease = scheduler.acquire(requires_gpu=args.verify_gpu and "gpu" in spec.capabilities, lease_id=spec.model_id)
        events.append({"event": "trial_started", "model_id": spec.model_id, "pid": lease.pid, "started_at": lease.started_at})
        trial_events.append(events[-1])
        try:
            if (
                not spec.available
                and spec.task != "foundation"
                and spec.library not in FOUNDATION_CANDIDATE_LIBRARIES
                and spec.library not in WORKER_SUBPROCESS_LIBRARIES
            ):
                result = unsupported_result(spec, trial_dir, "DEPENDENCY_MISSING", f"optional package missing: {spec.package}")
            elif spec.task == "candidate" and spec.library in FOUNDATION_CANDIDATE_LIBRARIES:
                result = run_foundation_candidate_lifecycle(spec, master, args, trial_dir)
            elif spec.task == "candidate":
                result = run_candidate_lifecycle(
                    spec,
                    master,
                    params={},
                    seed=args.seed,
                    output_dir=trial_dir,
                    device=args.device,
                    precision=args.precision,
                )
            elif spec.task == "foundation":
                result = run_foundation_lifecycle(spec, master, args, trial_dir)
            elif spec.task in {"position", "position_series", "candidate_series"}:
                result = run_worker_lifecycle(spec, master, args, trial_dir)
            else:
                result = unsupported_result(spec, trial_dir, "WORKER_NOT_IMPLEMENTED", f"task {spec.task} has no runtime validation worker")
        finally:
            scheduler.release(lease)
            events.append({"event": "trial_finished", "model_id": spec.model_id, "released_at": lease.released_at})
            trial_events.append(events[-1])
        requested = spec.default_params | {"seed": args.seed, "device": args.device, "precision": args.precision}
        effective = result.properties_after_fit or result.properties_before
        write_trial_artifacts(
            trial_dir,
            spec,
            result,
            requested=requested,
            effective=effective,
            config={"cli": cli_config, "model_id": spec.model_id, "run_signature": run_signature},
            trial_events=trial_events,
        )
        write_prediction_artifact(trial_dir / "predictions.parquet", result.predictions)
        if result.reloaded_predictions is not None:
            write_prediction_artifact(trial_dir / "reloaded_predictions.parquet", result.reloaded_predictions)
        if result.retrained_predictions is not None:
            write_prediction_artifact(trial_dir / "retrained_predictions.parquet", result.retrained_predictions)
        row = flatten_result(
            spec,
            result,
            run_id=run_id,
            run_signature=run_signature,
            catalog_info=catalog_info,
            data_sha256=data_sha256,
            code_fingerprint=code_fingerprint,
            required_lifecycle_flags=required_lifecycle_flags,
            device=args.device,
            precision=args.precision,
        )
        rows.append(row)
        for stage, props in (
            ("before", result.properties_before),
            ("after_fit", result.properties_after_fit),
            ("after_load", result.properties_after_load),
            ("after_retrain", result.properties_after_retrain),
        ):
            property_rows.append({"model_id": spec.model_id, "stage": stage, **props})
        for arg in result.argument_evidence:
            argument_rows.append({"model_id": spec.model_id, **arg})
        gpu_rows.append({"model_id": spec.model_id, **result.resource_evidence})
    write_jsonl(output_root / "events.jsonl", events)
    atomic_write_json(output_root / "process_tree.json", {"pid": lease.pid if specs else None})
    write_csv(output_root / "all_model_runtime_validation.csv", rows)
    status_payload = {
        "schema_version": 1,
        "catalog_source": catalog_info["catalog_source"],
        "catalog_total": catalog_info["catalog_count"],
        "executed": len(rows),
        "not_tested_count": 0,
        "counts": {},
        "rows": rows,
    }
    atomic_write_json(output_root / "all_model_runtime_validation.json", status_payload)
    write_csv(output_root / "model_property_matrix.csv", property_rows)
    write_csv(output_root / "argument_verification_matrix.csv", argument_rows)
    write_csv(output_root / "gpu_vram_matrix.csv", gpu_rows)
    write_csv(output_root / "parallel_execution_report.csv", scheduler.report())
    counts = pd.Series([row["final_status"] for row in rows]).value_counts().to_dict() if rows else {}
    status_payload["counts"] = counts
    atomic_write_json(output_root / "all_model_runtime_validation.json", status_payload)
    md_lines = [
        "# All Model Runtime Validation",
        "",
        f"run_id: `{run_id}`",
        f"data_version: `{manifest.data_version}`",
        "",
        "## Status Counts",
        "",
        *[f"- {key}: {value}" for key, value in counts.items()],
    ]
    (output_root / "all_model_runtime_validation.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    failures = [row for row in rows if row["final_status"] != "PASS"]
    (output_root / "failure_analysis.md").write_text(
        "\n".join(["# Failure Analysis", "", *[f"- {row['model_id']}: {row['final_status']} {row['failure_reason']}" for row in failures]]) + "\n",
        encoding="utf-8",
    )
    final_status_payload = {
        **status_payload,
        "run_id": run_id,
        "catalog_sha256": catalog_info["catalog_sha256"],
        "data_sha256": data_sha256,
        "code_fingerprint": code_fingerprint,
    }
    atomic_write_json(output_root / "run_summary.json", {"schema_version": 1, "run_id": run_id, "counts": counts, "models": len(rows), **catalog_info})
    atomic_write_json(output_root / "status.json", final_status_payload)
    if args.models == "all":
        atomic_write_json(output_base / "all_model_final_status.json", final_status_payload)
    print(json.dumps({"run_id": run_id, "output": str(output_root), "counts": counts}, ensure_ascii=False))
    return 0 if not any(row["final_status"] in {"FIT_FAILED", "PREDICT_FAILED"} for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
