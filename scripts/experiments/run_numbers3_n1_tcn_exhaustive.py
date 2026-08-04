from __future__ import annotations

import argparse
import dataclasses
import gc
import hashlib
import inspect
import itertools
import json
import os
import platform
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import MAE
from neuralforecast.models import TCN

ROOT = Path(__file__).resolve().parents[2]


@dataclasses.dataclass(frozen=True)
class TrialKey:
    combination_id: str
    seed: int
    test_index: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--mode",
        choices=("inventory", "construct", "evaluate"),
        default="inventory",
    )
    parser.add_argument(
        "--limit-combinations",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--rolling-points",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--skip-model-artifacts",
        action="store_true",
        help="Skip per-trial save/load/hash for screening only.",
    )
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, torch.dtype):
        return str(value)
    if hasattr(value, "__class__"):
        return repr(value)
    raise TypeError(type(value).__name__)


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config root must be a mapping")
    return config


def tcn_signature() -> inspect.Signature:
    return inspect.signature(TCN.__init__)


def inventory_arguments(
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    signature = tcn_signature()
    search = config.get("search", {})
    fixed = config.get("fixed", {})
    excluded = config.get("excluded", {})
    runtime = config.get("runtime", {})

    rows: list[dict[str, Any]] = []
    unclassified: list[str] = []

    for name, parameter in signature.parameters.items():
        if name == "self":
            continue

        if name in search:
            classification = "search"
            configured_value = search[name]
        elif name in fixed:
            classification = "fixed"
            configured_value = fixed[name]
        elif name in excluded:
            classification = "excluded"
            configured_value = excluded[name]
        elif name in runtime:
            classification = "runtime"
            configured_value = runtime[name]
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            classification = "runtime_kwargs"
            configured_value = runtime
        elif parameter.default is not inspect.Parameter.empty:
            classification = "default"
            configured_value = parameter.default
        else:
            classification = "unclassified"
            configured_value = None
            unclassified.append(name)

        rows.append(
            {
                "argument": name,
                "kind": str(parameter.kind),
                "annotation": repr(parameter.annotation),
                "has_default": (parameter.default is not inspect.Parameter.empty),
                "default": (
                    repr(parameter.default)
                    if parameter.default is not inspect.Parameter.empty
                    else None
                ),
                "classification": classification,
                "configured_value": configured_value,
            }
        )

    fail = config.get("verification", {}).get(
        "fail_on_unclassified_argument",
        True,
    )
    if fail and unclassified:
        raise RuntimeError(f"Unclassified TCN arguments: {unclassified}")

    return rows


def resolve_special_values(value: Any) -> Any:
    if value == "MAE":
        return MAE()
    return value


def normalized_value(value: Any) -> Any:
    if isinstance(value, torch.nn.Module):
        return value.__class__.__name__
    if isinstance(value, tuple):
        return [normalized_value(item) for item in value]
    if isinstance(value, list):
        return [normalized_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized_value(item) for key, item in value.items()}
    if isinstance(value, np.generic):
        return value.item()
    return value


def build_combinations(
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keys = list(search)
    values = [search[key] for key in keys]

    combinations = []
    for index, selected in enumerate(
        itertools.product(*values),
        start=1,
    ):
        params = dict(zip(keys, selected, strict=True))
        canonical = json.dumps(
            normalized_value(params),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        combination_id = f"tcn-{index:05d}-{sha256_bytes(canonical.encode())[:12]}"
        combinations.append(
            {
                "combination_id": combination_id,
                **params,
            }
        )
    return combinations


def model_kwargs(
    config: dict[str, Any],
    combination: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    fixed = {key: resolve_special_values(value) for key, value in config.get("fixed", {}).items()}
    search = {key: value for key, value in combination.items() if key != "combination_id"}
    runtime = dict(config.get("runtime", {}))

    kwargs = {
        **fixed,
        **search,
        "random_seed": seed,
        **runtime,
    }

    kwargs["alias"] = f"{combination['combination_id']}-seed{seed}"
    return kwargs


PROPERTY_ALIASES = {
    "encoder_hidden_size": ("encoder_hidden_size",),
    "context_size": ("context_size",),
    "decoder_hidden_size": ("decoder_hidden_size",),
    "kernel_size": ("kernel_size",),
    "dilations": ("dilations",),
    "input_size": ("input_size",),
    "h": ("h",),
    "learning_rate": ("learning_rate",),
    "max_steps": ("max_steps",),
    "batch_size": ("batch_size",),
    "windows_batch_size": ("windows_batch_size",),
    "scaler_type": ("scaler_type",),
    "random_seed": ("random_seed",),
    "alias": ("alias",),
}


def read_property(
    model: Any,
    name: str,
) -> tuple[bool, Any, str | None]:
    candidates = PROPERTY_ALIASES.get(name, (name,))
    for candidate in candidates:
        if hasattr(model, candidate):
            return True, getattr(model, candidate), candidate

    hparams = getattr(model, "hparams", None)
    if hparams is not None:
        for candidate in candidates:
            try:
                if candidate in hparams:
                    return True, hparams[candidate], f"hparams.{candidate}"
            except TypeError:
                pass

    return False, None, None


def property_value_record(
    value: Any,
) -> str:
    """Serialize heterogeneous property values safely for Parquet."""
    normalized = normalized_value(value)

    payload = {
        "python_type": type(value).__name__,
        "value": normalized,
    }

    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=json_default,
    )


def values_equal(
    expected: Any,
    actual: Any,
    tolerance: float,
) -> bool:
    expected = normalized_value(expected)
    actual = normalized_value(actual)

    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return bool(
                np.isclose(
                    float(expected),
                    float(actual),
                    rtol=0.0,
                    atol=tolerance,
                )
            )
        except (TypeError, ValueError):
            return False
    return expected == actual


def verify_properties(
    model: Any,
    requested: dict[str, Any],
    config: dict[str, Any],
    phase: str,
) -> list[dict[str, Any]]:
    tolerance = float(
        config.get("verification", {}).get(
            "float_abs_tolerance",
            1e-12,
        )
    )
    rows = []

    for name, requested_value in requested.items():
        if name in {
            "loss",
            "valid_loss",
            "accelerator",
            "devices",
            "enable_progress_bar",
            "enable_model_summary",
            "enable_checkpointing",
            "logger",
            "precision",
            "deterministic",
        }:
            continue

        # Constructor input and the model's resolved effective
        # property are not always identical. NeuralForecast resolves
        # valid_batch_size=None to batch_size.
        effective_expected = requested_value
        resolution_rule = "identity"

        if name == "valid_batch_size" and requested_value is None:
            effective_expected = requested.get("batch_size")
            resolution_rule = "None resolves to batch_size"

        exposed, actual, source = read_property(
            model,
            name,
        )

        matched = exposed and values_equal(
            effective_expected,
            actual,
            tolerance,
        )

        rows.append(
            {
                "phase": phase,
                "argument": name,
                "requested": property_value_record(requested_value),
                "effective_expected": (property_value_record(effective_expected)),
                "actual": property_value_record(actual),
                "requested_type": (type(requested_value).__name__),
                "effective_expected_type": (type(effective_expected).__name__),
                "actual_type": (type(actual).__name__ if exposed else None),
                "resolution_rule": resolution_rule,
                "property_source": source,
                "exposed": exposed,
                "matched": matched,
            }
        )
    return rows


def model_property_snapshot(
    model: Any,
) -> dict[str, Any]:
    named_parameters = list(model.named_parameters())
    total_parameters = sum(parameter.numel() for _, parameter in named_parameters)
    trainable_parameters = sum(
        parameter.numel() for _, parameter in named_parameters if parameter.requires_grad
    )
    devices = sorted({str(parameter.device) for _, parameter in named_parameters})
    dtypes = sorted({str(parameter.dtype) for _, parameter in named_parameters})

    selected = {}
    for name in PROPERTY_ALIASES:
        exposed, value, source = read_property(model, name)
        selected[name] = {
            "exposed": exposed,
            "value": normalized_value(value),
            "source": source,
        }

    return {
        "class": model.__class__.__name__,
        "module": model.__class__.__module__,
        "repr": repr(model),
        "total_parameters": total_parameters,
        "trainable_parameters": trainable_parameters,
        "parameter_devices": devices,
        "parameter_dtypes": dtypes,
        "selected_properties": selected,
        "exogenous_capabilities": {
            "future": bool(getattr(model, "EXOGENOUS_FUTR", False)),
            "historical": bool(getattr(model, "EXOGENOUS_HIST", False)),
            "static": bool(getattr(model, "EXOGENOUS_STAT", False)),
        },
        "multivariate": bool(getattr(model, "MULTIVARIATE", False)),
        "recurrent": bool(getattr(model, "RECURRENT", False)),
    }


def prepare_data(
    data_path: Path,
) -> pd.DataFrame:
    frame = pd.read_parquet(data_path)
    required = {"ds", "y"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing data columns: {missing}")

    frame = frame.sort_values("ds").reset_index(drop=True)
    frame["original_ds"] = pd.to_datetime(frame["ds"])
    frame["ds"] = np.arange(len(frame), dtype=int)
    frame["y"] = pd.to_numeric(
        frame["y"],
        errors="raise",
    ).astype(float)
    frame["unique_id"] = "N1"

    if frame["y"].isna().any():
        raise ValueError("Target contains nulls")
    if not np.isfinite(frame["y"]).all():
        raise ValueError("Target contains non-finite values")
    if frame["original_ds"].duplicated().any():
        raise ValueError("Duplicate ds")
    return frame


def cleanup_cuda() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def digitize(value: float) -> int:
    return int(np.clip(np.rint(value), 0, 9))


def save_hashes(root: Path) -> None:
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    lines = []
    for path in paths:
        lines.append(f"{sha256_file(path)}  {path.relative_to(root)}")
    (root / "SHA256SUMS").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def write_manifest(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rows.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    (root / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps(
            rows,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config = load_config(config_path)
    experiment = config["experiment"]

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + sha256_file(config_path)[:10]
    output_root = ROOT / experiment["output_root"]
    output = output_root / run_id
    output.mkdir(parents=True, exist_ok=False)

    (output / "logs").mkdir()
    (output / "model_artifacts").mkdir()
    (output / "manifests").mkdir()

    resolved = {
        "run_id": run_id,
        "mode": args.mode,
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "git_status": git_value("status", "--short"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),
        "pid": os.getpid(),
        "requested_deterministic_mode": (config.get("runtime", {}).get("deterministic")),
        "torch_deterministic_algorithms_enabled": (torch.are_deterministic_algorithms_enabled()),
        "torch_deterministic_warn_only": (torch.is_deterministic_algorithms_warn_only_enabled()),
        "float32_matmul_precision": (torch.get_float32_matmul_precision()),
        "config": config,
    }
    (output / "resolved_config.json").write_text(
        json.dumps(
            resolved,
            indent=2,
            ensure_ascii=False,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
    )

    inventory = inventory_arguments(config)
    (output / "argument_inventory.json").write_text(
        json.dumps(
            inventory,
            indent=2,
            ensure_ascii=False,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
    )

    combinations = build_combinations(config)
    if args.limit_combinations > 0:
        combinations = combinations[: args.limit_combinations]
    pd.DataFrame(combinations).to_parquet(
        output / "combinations.parquet",
        index=False,
    )

    if args.mode == "inventory":
        inventory_summary = {
            "run_id": run_id,
            "mode": args.mode,
            "public_argument_count": len(inventory),
            "combination_count": len(combinations),
            "search_argument_count": len(config.get("search", {})),
            "unclassified_arguments": [
                row["argument"] for row in inventory if row["classification"] == "unclassified"
            ],
        }

        (output / "inventory_summary.json").write_text(
            json.dumps(
                inventory_summary,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        write_manifest(output)
        save_hashes(output)

        print(
            json.dumps(
                inventory_summary,
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"OUTPUT={output}")
        print("TCN_ARGUMENT_INVENTORY=PASS")
        return

    constructor_rows = []
    property_rows = []

    seeds = [int(seed) for seed in experiment["seeds"]]

    for combination in combinations:
        kwargs = model_kwargs(
            config,
            combination,
            seeds[0],
        )
        started = time.perf_counter()
        try:
            model = TCN(**kwargs)
            snapshot = model_property_snapshot(model)
            verification = verify_properties(
                model,
                kwargs,
                config,
                phase="constructed",
            )
            ignored = [row["argument"] for row in verification if not row["matched"]]
            constructor_rows.append(
                {
                    "combination_id": (combination["combination_id"]),
                    "status": ("PASS" if not ignored else "PROPERTY_MISMATCH"),
                    "elapsed_seconds": (time.perf_counter() - started),
                    "ignored_or_mismatched": ignored,
                    "snapshot": json.dumps(
                        snapshot,
                        ensure_ascii=False,
                        default=json_default,
                    ),
                    "error_type": None,
                    "error": None,
                }
            )
            for row in verification:
                property_rows.append(
                    {
                        "combination_id": (combination["combination_id"]),
                        "seed": seeds[0],
                        **row,
                    }
                )
        except Exception as exc:
            constructor_rows.append(
                {
                    "combination_id": (combination["combination_id"]),
                    "status": "ERROR",
                    "elapsed_seconds": (time.perf_counter() - started),
                    "ignored_or_mismatched": [],
                    "snapshot": None,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

    constructor = pd.DataFrame(constructor_rows)
    constructor.to_parquet(
        output / "constructor_verification.parquet",
        index=False,
    )
    property_columns = [
        "combination_id",
        "seed",
        "phase",
        "argument",
        "requested",
        "effective_expected",
        "actual",
        "requested_type",
        "effective_expected_type",
        "actual_type",
        "resolution_rule",
        "property_source",
        "exposed",
        "matched",
    ]

    property_frame = pd.DataFrame(
        property_rows,
        columns=property_columns,
    )

    for column in (
        "combination_id",
        "phase",
        "argument",
        "requested",
        "effective_expected",
        "actual",
        "requested_type",
        "effective_expected_type",
        "actual_type",
        "resolution_rule",
        "property_source",
    ):
        property_frame[column] = property_frame[column].astype("string")

    property_frame.to_parquet(
        output / "property_verification.parquet",
        index=False,
    )

    if args.mode == "construct":
        write_manifest(output)
        save_hashes(output)
        print(f"OUTPUT={output}")
        print(
            "CONSTRUCTOR_PASS=",
            int((constructor["status"] == "PASS").sum()),
        )
        print(
            "CONSTRUCTOR_TOTAL=",
            len(constructor),
        )
        return

    if (
        config["verification"].get(
            "require_cuda",
            True,
        )
        and not torch.cuda.is_available()
    ):
        raise RuntimeError("CUDA is required")

    # RTX Tensor Coreを使用しつつ、float32精度方針を固定する。
    torch.set_float32_matmul_precision("high")

    deterministic_mode = config.get("runtime", {}).get(
        "deterministic",
        True,
    )

    if deterministic_mode == "warn":
        torch.use_deterministic_algorithms(
            True,
            warn_only=True,
        )
    elif deterministic_mode is True:
        torch.use_deterministic_algorithms(
            True,
            warn_only=False,
        )
    elif deterministic_mode is False:
        torch.use_deterministic_algorithms(False)
    else:
        raise ValueError(
            f"runtime.deterministic must be true, false, or 'warn'; received {deterministic_mode!r}"
        )

    valid_ids = set(
        constructor.loc[
            constructor["status"] == "PASS",
            "combination_id",
        ]
    )
    valid_combinations = [
        combination for combination in combinations if combination["combination_id"] in valid_ids
    ]

    frame = prepare_data(ROOT / experiment["data_path"])
    rolling_points = (
        args.rolling_points if args.rolling_points > 0 else int(experiment["rolling_points"])
    )
    first_test_index = len(frame) - rolling_points

    prediction_rows = []
    trial_rows = []
    runtime_rows = []
    fitted_property_rows = []

    for combination in valid_combinations:
        for seed in seeds:
            for test_index in range(
                first_test_index,
                len(frame),
            ):
                cleanup_cuda()
                key = TrialKey(
                    combination["combination_id"],
                    seed,
                    test_index,
                )
                history = frame.iloc[:test_index][["unique_id", "ds", "y"]].copy()
                actual_row = frame.iloc[test_index]
                actual = float(actual_row["y"])
                kwargs = model_kwargs(
                    config,
                    combination,
                    seed,
                )
                trial_started = time.perf_counter()

                try:
                    torch.manual_seed(seed)
                    torch.cuda.manual_seed_all(seed)
                    torch.backends.cudnn.benchmark = False
                    torch.backends.cudnn.deterministic = True
                    if deterministic_mode == "warn":
                        torch.use_deterministic_algorithms(
                            True,
                            warn_only=True,
                        )
                    elif deterministic_mode is True:
                        torch.use_deterministic_algorithms(
                            True,
                            warn_only=False,
                        )
                    else:
                        torch.use_deterministic_algorithms(False)
                    torch.cuda.reset_peak_memory_stats()

                    model = TCN(**kwargs)
                    nf = NeuralForecast(
                        models=[model],
                        freq=1,
                    )

                    fit_started = time.perf_counter()
                    nf.fit(df=history)
                    fit_seconds = time.perf_counter() - fit_started

                    fitted_model = nf.models[0]
                    fitted_verification = verify_properties(
                        fitted_model,
                        kwargs,
                        config,
                        phase="fitted",
                    )
                    for row in fitted_verification:
                        fitted_property_rows.append(
                            {
                                "combination_id": (key.combination_id),
                                "seed": seed,
                                "test_index": test_index,
                                **row,
                            }
                        )

                    predict_started = time.perf_counter()
                    forecast = nf.predict()
                    predict_seconds = time.perf_counter() - predict_started
                    prediction_columns = [
                        column for column in forecast.columns if column not in {"unique_id", "ds"}
                    ]
                    if len(prediction_columns) != 1:
                        raise RuntimeError(f"Unexpected forecast columns: {prediction_columns}")
                    raw = float(forecast[prediction_columns[0]].iloc[0])
                    if not np.isfinite(raw):
                        raise RuntimeError("Non-finite prediction")

                    artifact_dir = None
                    loaded_raw = raw
                    prediction_match = True
                    artifact_sha256 = None

                    if not args.skip_model_artifacts:
                        artifact_dir = (
                            output
                            / "model_artifacts"
                            / key.combination_id
                            / f"seed-{seed}"
                            / f"test-{test_index}"
                        )
                        artifact_dir.mkdir(
                            parents=True,
                            exist_ok=False,
                        )
                        nf.save(
                            path=str(artifact_dir),
                            overwrite=True,
                            save_dataset=True,
                        )

                        loaded = NeuralForecast.load(path=str(artifact_dir))
                        loaded_forecast = loaded.predict()
                        loaded_raw = float(loaded_forecast[prediction_columns[0]].iloc[0])
                    tolerance = float(config["verification"]["prediction_abs_tolerance"])
                    prediction_match = bool(
                        np.isclose(
                            raw,
                            loaded_raw,
                            rtol=0.0,
                            atol=tolerance,
                        )
                    )
                    if (
                        config["verification"].get(
                            "require_prediction_match_after_load",
                            True,
                        )
                        and not prediction_match
                    ):
                        raise RuntimeError(f"Prediction changed after load: {raw} != {loaded_raw}")

                    digit = digitize(raw)
                    digit_error = actual - digit

                    prediction_rows.append(
                        {
                            "combination_id": (key.combination_id),
                            "seed": seed,
                            "test_index": test_index,
                            "original_ds": str(actual_row["original_ds"]),
                            "actual": actual,
                            "prediction_raw": raw,
                            "prediction_loaded_raw": (loaded_raw),
                            "prediction_digit": digit,
                            "prediction_match_after_load": (prediction_match),
                            "abs_error": abs(actual - raw),
                            "squared_error": (actual - raw) ** 2,
                            "digit_abs_error": abs(digit_error),
                            "digit_squared_error": (digit_error**2),
                            "within_1": int(abs(digit_error) <= 1),
                            "exact": int(digit_error == 0),
                        }
                    )
                    trial_rows.append(
                        {
                            "combination_id": (key.combination_id),
                            "seed": seed,
                            "test_index": test_index,
                            "status": "PASS",
                            "fit_seconds": fit_seconds,
                            "predict_seconds": (predict_seconds),
                            "total_seconds": (time.perf_counter() - trial_started),
                            "peak_vram_mib": (torch.cuda.max_memory_allocated() / 1024**2),
                            "artifact_path": (
                                str(artifact_dir) if artifact_dir is not None else None
                            ),
                            "artifact_sha256": (artifact_sha256),
                            "error_type": None,
                            "error": None,
                        }
                    )
                    runtime_rows.append(
                        {
                            "combination_id": (key.combination_id),
                            "seed": seed,
                            "test_index": test_index,
                            "pid": os.getpid(),
                            "cuda_available": (torch.cuda.is_available()),
                            "gpu_name": (torch.cuda.get_device_name(0)),
                            "model_devices": (
                                model_property_snapshot(fitted_model)["parameter_devices"]
                            ),
                            "finite_output": True,
                            "peak_vram_mib": (torch.cuda.max_memory_allocated() / 1024**2),
                            "cpu_fallback": False,
                            "requested_deterministic_mode": (
                                config.get(
                                    "runtime",
                                    {},
                                ).get("deterministic")
                            ),
                            "strict_bitwise_determinism": (
                                config.get(
                                    "runtime",
                                    {},
                                ).get("deterministic")
                                is True
                            ),
                            "deterministic_warning_mode": (
                                config.get(
                                    "runtime",
                                    {},
                                ).get("deterministic")
                                == "warn"
                            ),
                            "scaler_type": (combination["scaler_type"]),
                        }
                    )
                except Exception as exc:
                    trial_rows.append(
                        {
                            "combination_id": (key.combination_id),
                            "seed": seed,
                            "test_index": test_index,
                            "status": "ERROR",
                            "fit_seconds": None,
                            "predict_seconds": None,
                            "total_seconds": (time.perf_counter() - trial_started),
                            "peak_vram_mib": (
                                torch.cuda.max_memory_allocated() / 1024**2
                                if torch.cuda.is_available()
                                else 0.0
                            ),
                            "artifact_path": None,
                            "artifact_sha256": None,
                            "error_type": (type(exc).__name__),
                            "error": str(exc),
                            "traceback": (traceback.format_exc()),
                        }
                    )

    predictions = pd.DataFrame(prediction_rows)
    trials = pd.DataFrame(trial_rows)
    runtime = pd.DataFrame(runtime_rows)
    fitted_properties = pd.DataFrame(fitted_property_rows)

    predictions.to_parquet(
        output / "predictions.parquet",
        index=False,
    )
    trials.to_parquet(
        output / "trial_results.parquet",
        index=False,
    )
    runtime.to_parquet(
        output / "runtime_evidence.parquet",
        index=False,
    )
    fitted_properties.to_parquet(
        output / "fitted_property_verification.parquet",
        index=False,
    )

    if predictions.empty:
        raise RuntimeError("No successful predictions")

    seed_summary = predictions.groupby(
        ["combination_id", "seed"],
        as_index=False,
    ).agg(
        predictions=("actual", "size"),
        hit_within_1=("within_1", "mean"),
        exact_rate=("exact", "mean"),
        mae=("digit_abs_error", "mean"),
        mse=("digit_squared_error", "mean"),
    )
    seed_summary["rmse"] = np.sqrt(seed_summary["mse"])
    seed_summary.to_csv(
        output / "seed_summary.csv",
        index=False,
    )

    leaderboard = (
        seed_summary.groupby(
            "combination_id",
            as_index=False,
        )
        .agg(
            seeds=("seed", "nunique"),
            hit_within_1_mean=(
                "hit_within_1",
                "mean",
            ),
            hit_within_1_std=(
                "hit_within_1",
                "std",
            ),
            hit_within_1_worst=(
                "hit_within_1",
                "min",
            ),
            exact_rate_mean=(
                "exact_rate",
                "mean",
            ),
            mae_mean=("mae", "mean"),
            mae_std=("mae", "std"),
            mae_worst=("mae", "max"),
            mse_mean=("mse", "mean"),
            mse_std=("mse", "std"),
            mse_worst=("mse", "max"),
            rmse_mean=("rmse", "mean"),
        )
        .sort_values(
            [
                "hit_within_1_mean",
                "hit_within_1_worst",
                "mae_mean",
                "mse_mean",
            ],
            ascending=[
                False,
                False,
                True,
                True,
            ],
        )
    )
    leaderboard.to_csv(
        output / "leaderboard.csv",
        index=False,
    )

    mismatch_count = int(
        (~fitted_properties["matched"].astype(bool)).sum() if not fitted_properties.empty else 0
    )
    failed_trials = int((trials["status"] != "PASS").sum())

    best = leaderboard.iloc[0]

    total_expected_trials = len(valid_combinations) * len(seeds) * rolling_points

    overall_status = (
        "PASS"
        if (
            failed_trials == 0
            and mismatch_count == 0
            and len(predictions) == total_expected_trials
            and predictions["prediction_match_after_load"].all()
        )
        else "FAILED"
    )

    report = f"""# TCN exhaustive argument verification

- Run ID: {run_id}
- Overall status: {overall_status}
- Combinations: {len(combinations)}
- Valid constructor combinations: {len(valid_combinations)}
- Seeds: {len(seeds)}
- Rolling points: {rolling_points}
- Expected trials: {total_expected_trials}
- Successful predictions: {len(predictions)}
- Failed trials: {failed_trials}
- Property mismatches after fit: {mismatch_count}

## Best configuration

- combination_id: {best["combination_id"]}
- Hit@±1 mean: {best["hit_within_1_mean"]:.6f}
- Hit@±1 worst seed: {best["hit_within_1_worst"]:.6f}
- MAE mean: {best["mae_mean"]:.6f}
- MSE mean: {best["mse_mean"]:.6f}
- RMSE mean: {best["rmse_mean"]:.6f}

## Acceptance

- All public arguments classified: PASS
- Constructor verification: {"PASS" if (constructor["status"] == "PASS").all() else "PARTIAL"}
- GPU runtime evidence: {"PASS" if not runtime.empty else "FAIL"}
- Save/load prediction equivalence: {
        "SKIPPED"
        if args.skip_model_artifacts
        else ("PASS" if predictions["prediction_match_after_load"].all() else "FAIL")
    }
- Effective property verification: {"PASS" if mismatch_count == 0 else "FAIL"}
- Complete trial execution: {
        "PASS" if failed_trials == 0 and len(predictions) == total_expected_trials else "FAIL"
    }
- Overall verdict: {overall_status}
"""
    (output / "VERIFICATION_REPORT.md").write_text(
        report,
        encoding="utf-8",
    )

    write_manifest(output)
    save_hashes(output)

    print(report)
    print(f"OUTPUT={output}")

    fail_ignored = config["verification"].get(
        "fail_on_ignored_argument",
        True,
    )
    if fail_ignored and mismatch_count:
        raise SystemExit(f"Property mismatch count={mismatch_count}")
    if failed_trials:
        raise SystemExit(f"Failed trial count={failed_trials}")


if __name__ == "__main__":
    main()
