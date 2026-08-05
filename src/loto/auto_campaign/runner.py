from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from loto.auto_campaign.p1_compat import (
    install_p1_runtime_compatibility,
    prepare_auto_model_config,
)

from .accuracy import filter_tasks_by_promotion
from .api_coverage import api_case_plan
from .arguments import build_argument_catalog, runtime_signature_catalog
from .contracts import CampaignConfig, CampaignStage
from .coverage import build_pairwise_plan, coverage_report
from .data_tracks import (
    build_panel,
    holdout_origins,
    load_miniloto,
    oof_origins,
    pre_holdout_frame,
)
from .domains import add_random_representatives, describe_config
from .evaluation import summarize_metrics
from .metrics import prediction_variants, score_draw_matrix, select_point_column
from .model_factory import build_auto_model
from .persistence import (
    save_best_model_bundle,
    sha256_file,
    verify_sha256s,
    write_json,
    write_sha256s,
)  # noqa: E501
from .registry import AutoModelRecord, discover_auto_models, get_default_config
from .resources import apply_model_resource_profile, resource_profile_name
from .runtime import (
    code_environment_fingerprint,
    compare_code_fingerprints,
    gpu_process_snapshot,
    torch_runtime_snapshot,
)
from .tasks import CampaignTask, build_tasks

install_p1_runtime_compatibility()


def load_config(path: Path) -> CampaignConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CampaignConfig.model_validate(payload)


def _git_snapshot(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(args, cwd=root, capture_output=True, text=True, check=False)
        return result.stdout.strip()

    return {
        "commit": run("git", "rev-parse", "HEAD"),
        "status": run("git", "status", "--short"),
    }


def _code_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    candidates: list[Path] = []
    for relative in (
        Path("src/loto/auto_campaign"),
        Path("configs/auto_campaign"),
        Path("scripts/experiments"),
    ):
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                if (
                    relative == Path("scripts/experiments")
                    and "all_neuralforecast_auto" not in path.name
                ):
                    continue
                candidates.append(path)
    for path in sorted(candidates):
        relative_name = path.relative_to(root).as_posix()
        digest.update(relative_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    return repr(value)


def _parquet_safe_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Serialize nested or heterogeneous object columns for Parquet."""

    frame = pd.DataFrame(rows)
    for column in frame.columns:
        if frame[column].dtype != "object":
            continue
        values = [value for value in frame[column].tolist() if value is not None]
        types = {type(value) for value in values}
        nested = any(isinstance(value, (dict, list, tuple, set, np.ndarray)) for value in values)
        if nested or len(types) > 1:
            frame[column] = frame[column].map(
                lambda value: json.dumps(
                    _jsonable(value),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    return frame


def _value_matches(requested: Any, effective: Any) -> bool:
    if isinstance(requested, (int, float)) and isinstance(effective, (int, float)):
        return bool(np.isclose(float(requested), float(effective), rtol=1e-8, atol=1e-10))
    return requested == effective or repr(requested) == repr(effective)


def _normalized_effective_value(
    key: str,
    requested_value: Any,
    requested: dict[str, Any],
    model: Any | None,
) -> Any | None:
    if model is None:
        return None
    recurrent = bool(getattr(model, "RECURRENT", False))
    h = int(requested.get("h", getattr(model, "h", 1)) or 1)
    if key == "input_size" and isinstance(requested_value, (int, float)):
        value = 3 * h if requested_value < 1 else int(requested_value)
        return value + 1 if recurrent else value
    if key == "inference_input_size" and (
        requested_value is None or isinstance(requested_value, (int, float))
    ):
        input_requested = requested.get("input_size", requested_value)
        if isinstance(input_requested, (int, float)):
            value = 3 * h if input_requested < 1 else int(input_requested)
            return value + 1 if recurrent else value
    return None


def _config_diff(
    requested: dict[str, Any],
    effective: dict[str, Any],
    *,
    model: Any | None = None,
) -> dict[str, Any]:
    ignored = {"callbacks", "logger", "enable_progress_bar", "enable_checkpointing"}
    items: dict[str, Any] = {}
    failures: list[str] = []
    for key, requested_value in sorted(requested.items()):
        if key in ignored:
            continue
        if key not in effective:
            status = "NOT_EXPOSED"
            failures.append(key)
            effective_value = None
        else:
            effective_value = effective[key]
            if _value_matches(requested_value, effective_value):
                status = "MATCH"
            else:
                normalized = _normalized_effective_value(
                    key,
                    requested_value,
                    requested,
                    model,
                )
                if normalized is not None and _value_matches(
                    normalized,
                    effective_value,
                ):
                    status = "NORMALIZED_BY_MODEL"
                else:
                    status = "MISMATCH"
                    failures.append(key)
        items[key] = {
            "requested": _jsonable(requested_value),
            "effective": _jsonable(effective_value),
            "status": status,
            "strict": True,
        }
    return {
        "status": "PASS" if not failures else "FAIL",
        "strict_failure_count": len(failures),
        "strict_failures": failures,
        "items": items,
    }


def _require_single_fitted_model(nf: Any) -> Any:
    """Return the single fitted AutoModel that `NeuralForecast.fit()` produced.

    `NeuralForecast(models=[...])` deep-copies its inputs (core.py
    `_reset_models`), so the caller's pre-construction `auto_model` reference
    is never the object that actually got fit. All post-fit
    inspection/persistence must use `nf.models[0]`, never the original.
    """
    if len(nf.models) != 1:
        raise RuntimeError(f"Expected one fitted AutoModel, got {len(nf.models)}")
    return nf.models[0]


def _effective_config(auto_model: Any) -> dict[str, Any]:
    inner = getattr(auto_model, "model", None)
    if inner is None:
        return {}

    def hparams_for(model: Any) -> dict[str, Any]:
        hparams = getattr(model, "hparams", None)
        if hparams is None:
            return {}
        try:
            return dict(hparams)
        except Exception:
            return {key: getattr(hparams, key) for key in dir(hparams) if not key.startswith("_")}

    values = hparams_for(inner)
    nested = getattr(inner, "model", None)
    if nested is not None and nested is not inner:
        # HINT wraps a base model. Its effective configuration is the union of
        # reconciliation settings and the wrapped model hyperparameters.
        values = {**hparams_for(nested), **values}
        values["wrapped_model_class"] = type(nested).__name__
    return {"model_class": type(inner).__name__, **_jsonable(values)}


def _result_trials(auto_model: Any, backend: str) -> list[dict[str, Any]]:
    results = getattr(auto_model, "results", None)
    rows: list[dict[str, Any]] = []
    if results is None:
        return rows
    if backend == "ray":
        for index, result in enumerate(results):
            checkpoint = getattr(getattr(result, "checkpoint", None), "path", None)
            rows.append(
                {
                    "trial_index": index,
                    "status": "PASS" if getattr(result, "error", None) is None else "FAIL",
                    "config": _jsonable(getattr(result, "config", {})),
                    "metrics": _jsonable(getattr(result, "metrics", {})),
                    "path": str(getattr(result, "path", "")),
                    "checkpoint": checkpoint,
                    "error": repr(getattr(result, "error", None)),
                }
            )
    else:
        for trial in results.trials:
            rows.append(
                {
                    "trial_index": trial.number,
                    "status": str(trial.state),
                    "config": _jsonable(trial.user_attrs.get("ALL_PARAMS", trial.params)),
                    "metrics": _jsonable(trial.user_attrs.get("METRICS", {})),
                    "path": "",
                    "checkpoint": "",
                    "error": None,
                }
            )
    return rows


def _copy_trial_artifacts(
    source_root: Path,
    target_root: Path,
    *,
    require_checkpoint: bool,
) -> dict[str, Any]:
    target_root.mkdir(parents=True, exist_ok=True)
    trials = sorted(
        path
        for path in source_root.glob("trial_*")
        if path.is_dir() and not path.name.endswith(".partial")
    )
    failures: list[str] = []
    copied_successful = 0
    failed_trials = 0
    for source in trials:
        target = target_root / source.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        trial_manifest_path = target / "manifest.json"
        trial_manifest = (
            json.loads(trial_manifest_path.read_text(encoding="utf-8"))
            if trial_manifest_path.is_file()
            else {}
        )
        successful = trial_manifest.get("status") == "PASS"
        if successful:
            verification_path = target / "load_predict_verification.json"
            verification = (
                json.loads(verification_path.read_text(encoding="utf-8"))
                if verification_path.is_file()
                else {}
            )
            if require_checkpoint and not (target / "model.ckpt").is_file():
                failures.append(f"missing checkpoint for successful trial: {target}")
            elif verification.get("status") != "PASS":
                failures.append(f"trial load verification failed: {target}")
            elif verification.get("cpu_fallback"):
                failures.append(f"trial CPU fallback: {target}")
            else:
                copied_successful += 1
        else:
            failed_trials += 1
        write_sha256s(target)
    return {
        "trial_count": len(trials),
        "copied": copied_successful,
        "failed_trials": failed_trials,
        "failures": failures,
    }


def _verify_worker_code_fingerprints(
    trials_root: Path,
    driver_fingerprint: dict[str, Any],
) -> dict[str, Any]:
    """Compare every successful trial's worker-captured fingerprint to the driver's.

    A missing fingerprint file on a successful trial is treated the same as a
    mismatch: it means we cannot prove the worker ran the code we think it
    did, which is exactly the failure mode this check exists to catch.
    """

    trial_dirs = sorted(
        path
        for path in trials_root.glob("trial_*")
        if path.is_dir() and not path.name.endswith(".partial")
    )
    per_trial: dict[str, Any] = {}
    missing: list[str] = []
    mismatched: list[str] = []
    for trial_dir in trial_dirs:
        manifest_path = trial_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "PASS":
            continue
        fingerprint_path = trial_dir / "worker_code_fingerprint.json"
        if not fingerprint_path.is_file():
            missing.append(trial_dir.name)
            continue
        worker_fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        comparison = compare_code_fingerprints(driver_fingerprint, worker_fingerprint)
        per_trial[trial_dir.name] = comparison
        if comparison["status"] != "PASS":
            mismatched.append(trial_dir.name)
    return {
        "status": "PASS" if not missing and not mismatched else "FAIL",
        "missing_fingerprint_trials": missing,
        "mismatched_trials": mismatched,
        "per_trial": per_trial,
    }


def _task_output(run_root: Path, task: CampaignTask) -> Path:
    return run_root / "tasks" / Path(task.key)


def _selection_name(task: CampaignTask) -> str:
    suffix = "shared" if task.position is None else f"p{task.position}"
    return f"{task.model_name}__{task.track}__{suffix}"


def _best_config(auto_model: Any, backend: str) -> dict[str, Any]:
    results = getattr(auto_model, "results", None)
    if results is None:
        return {}
    if backend == "ray":
        raw = dict(results.get_best_result().config)
    else:
        raw = dict(results.best_trial.user_attrs.get("ALL_PARAMS", {}))
    for protected in ("h", "loss", "valid_loss", "callbacks"):
        raw.pop(protected, None)
    return _jsonable(raw)


def _training_frame_for_stage(
    frame: pd.DataFrame,
    config: CampaignConfig,
    task: CampaignTask,
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict[str, Any]]:
    stage = CampaignStage(task.stage)
    if stage in {CampaignStage.SMOKE, CampaignStage.COVERAGE, CampaignStage.HPO}:
        train = pre_holdout_frame(frame, config)
        return (
            train,
            None,
            {"val_size": min(config.split.validation_draws, max(1, len(train) // 4))},
        )  # noqa: E501
    if stage == CampaignStage.VALIDATE_TRIALS:
        if task.origin is None:
            raise ValueError("validation replay task requires origin")
        train = frame.iloc[: task.origin].copy()
        actual = frame.iloc[task.origin : task.origin + 1].copy()
        return (
            train,
            actual,
            {"val_size": min(config.split.oof_validation_draws, max(1, len(train) // 4))},
        )
    if stage == CampaignStage.HOLDOUT:
        if task.origin is None:
            raise ValueError("holdout task requires origin")
        train = frame.iloc[: task.origin].copy()
        actual = frame.iloc[task.origin : task.origin + 1].copy()
        return (
            train,
            actual,
            {"val_size": min(config.split.validation_draws, max(1, len(train) // 4))},
        )  # noqa: E501
    if stage == CampaignStage.OOF:
        if task.origin is None:
            raise ValueError("OOF task requires endpoint origin")
        train = frame.iloc[: task.origin].copy()
        actual = frame.iloc[task.origin : task.origin + 1].copy()
        return (
            train,
            actual,
            {"val_size": min(config.split.oof_validation_draws, max(1, len(train) // 4))},
        )  # noqa: E501
    if stage == CampaignStage.PROSPECTIVE:
        return (
            frame.copy(),
            None,
            {"val_size": min(config.split.validation_draws, max(1, len(frame) // 4))},
        )  # noqa: E501
    raise ValueError(f"unsupported execution stage: {stage}")


def execute_task(
    *,
    project_root: Path,
    run_root: Path,
    frame: pd.DataFrame,
    contract: Any,
    config: CampaignConfig,
    task: CampaignTask,
    num_samples: int,
    smoke: bool,
    fixed_config: dict[str, Any] | None = None,
    backend_override: str | None = None,
) -> dict[str, Any]:
    output = _task_output(run_root, task)
    if output.exists():
        manifest_path = output / "manifest.json"
        if manifest_path.is_file():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("status") == "PASS":
                return existing
        raise FileExistsError(output)

    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    train_frame, actual_frame, split_args = _training_frame_for_stage(frame, config, task)
    panel = build_panel(train_frame, contract, track=task.track, position=task.position)
    train_nf = panel[["unique_id", "ds", "y"]].copy()
    n_series = 6 if task.track == "h_hint" else (5 if task.track == "m_joint" else None)
    alias = f"{task.model_name}_{task.track}_s{task.seed}"
    execution_backend = backend_override or task.backend
    trial_temp = run_root / "trial_work" / Path(task.key)
    trial_temp.mkdir(parents=True, exist_ok=True)
    driver_code_fingerprint = code_environment_fingerprint()

    auto_model, requested_config, base_kwargs = build_auto_model(
        model_name=task.model_name,
        config=config,
        backend=execution_backend,
        alias=alias,
        trial_root=trial_temp,
        n_series=n_series,
        num_samples=num_samples,
        seed=task.seed,
        smoke=smoke,
        fixed_config=fixed_config,
        preserve_fixed_random_seed=(
            CampaignStage(task.stage) in {CampaignStage.COVERAGE, CampaignStage.VALIDATE_TRIALS}
        ),
    )
    requested_config = prepare_auto_model_config(
        auto_model,
        requested_config,
        model_name=task.model_name,
    )
    from neuralforecast import NeuralForecast

    nf_kwargs = {
        "models": [auto_model],
        "freq": config.freq,
        "local_scaler_type": config.local_scaler_type,
        "local_static_scaler_type": config.local_static_scaler_type,
        **config.extra_neuralforecast_args,
    }
    fit_kwargs = {
        "df": train_nf,
        "static_df": None,
        "val_size": split_args["val_size"],
        "val_df": None,
        "use_init_models": False,
        "verbose": False,
        "id_col": "unique_id",
        "time_col": "ds",
        "target_col": "y",
        "distributed_config": None,
        "prediction_intervals": None,
        **config.extra_fit_args,
    }
    nf = NeuralForecast(**nf_kwargs)
    nf.fit(**fit_kwargs)
    fitted_auto_model = _require_single_fitted_model(nf)
    prediction_before = nf.predict()
    point_column = select_point_column(prediction_before, alias)
    if not np.isfinite(prediction_before[point_column].to_numpy(dtype=float)).all():
        raise RuntimeError("non-finite predictions")

    runtime = torch_runtime_snapshot(getattr(fitted_auto_model, "model", None))
    gpu_pid = gpu_process_snapshot()
    effective = _effective_config(fitted_auto_model)
    trial_rows = _result_trials(fitted_auto_model, execution_backend)
    selected_config = _best_config(fitted_auto_model, execution_backend)

    bundle_target = output / "best_model"
    requested_for_compare = selected_config if selected_config else _jsonable(requested_config)
    if not isinstance(requested_for_compare, dict):
        requested_for_compare = {}
    config_diff = _config_diff(
        requested_for_compare,
        effective,
        model=getattr(fitted_auto_model, "model", None),
    )

    bundle_manifest = save_best_model_bundle(
        nf=nf,
        auto_model=fitted_auto_model,
        target=bundle_target,
        train_panel=train_nf,
        prediction_before=prediction_before,
        requested_config=_jsonable(requested_config),
        effective_config=effective,
        base_auto_args=_jsonable(base_kwargs),
        neuralforecast_args=_jsonable(
            {key: value for key, value in nf_kwargs.items() if key != "models"}
        ),  # noqa: E501
        fit_args=_jsonable({key: value for key, value in fit_kwargs.items() if key != "df"}),
        runtime=runtime,
        gpu_pid=gpu_pid,
        save_dataset=config.persistence.save_dataset,
        atomic=config.persistence.atomic_write,
    )

    write_json(bundle_target / "config_diff.json", config_diff)
    write_sha256s(bundle_target)
    if config_diff["status"] != "PASS":
        raise RuntimeError(f"effective configuration mismatch: {config_diff['strict_failures']}")

    # Reload and predict: formal certification is not based on files merely existing.
    load_verify: dict[str, Any] = {"status": "SKIPPED"}
    if config.persistence.verify_load_predict:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
        except ImportError:
            pass
        loaded = NeuralForecast.load(str(bundle_target / "neuralforecast"))
        prediction_after = loaded.predict()
        prediction_after.to_parquet(bundle_target / "prediction_after_load.parquet", index=False)
        before_values = prediction_before[point_column].to_numpy(dtype=float)
        after_point = select_point_column(prediction_after, alias)
        after_values = prediction_after[after_point].to_numpy(dtype=float)
        load_verify = {
            "loaded": True,
            "predicted": True,
            "shape_match": before_values.shape == after_values.shape,
            "finite": bool(np.isfinite(after_values).all()),
            "prediction_match": bool(
                np.allclose(before_values, after_values, rtol=1e-6, atol=1e-6)
            ),  # noqa: E501
            "max_abs_diff": float(np.max(np.abs(before_values - after_values))),
            "runtime": torch_runtime_snapshot(getattr(loaded.models[0], "model", None)),
            "gpu_pid": gpu_process_snapshot(),
        }
        load_verify["cuda_execution_evidence"] = bool(
            str(load_verify["runtime"].get("trainer_root_device", "")).startswith("cuda")
            or load_verify["runtime"].get("cuda_peak_memory_allocated", 0) > 0
        )
        load_verify["cpu_fallback"] = not load_verify["cuda_execution_evidence"]
        load_verify["status"] = (
            "PASS"
            if load_verify["shape_match"]
            and load_verify["finite"]
            and load_verify["prediction_match"]
            and not load_verify["cpu_fallback"]
            else "FAIL"
        )
        write_json(bundle_target / "load_predict_verification.json", load_verify)
        bundle_payload = json.loads((bundle_target / "manifest.json").read_text(encoding="utf-8"))
        bundle_payload.update(
            {
                "config_status": config_diff["status"],
                "load_predict_status": load_verify["status"],
                "prediction_after_sha256": sha256_file(
                    bundle_target / "prediction_after_load.parquet"
                ),
                "prediction_match": load_verify["prediction_match"],
                "cpu_fallback": load_verify["cpu_fallback"],
            }
        )
        write_json(bundle_target / "manifest.json", bundle_payload)
        write_sha256s(bundle_target)
        if load_verify["status"] != "PASS":
            raise RuntimeError(f"load/predict verification failed: {load_verify}")

    trial_summary = _copy_trial_artifacts(
        trial_temp,
        output / "trials",
        require_checkpoint=config.persistence.require_trial_checkpoint,
    )
    write_json(output / "driver_code_fingerprint.json", driver_code_fingerprint)
    code_fingerprint_comparison = _verify_worker_code_fingerprints(
        output / "trials",
        driver_code_fingerprint,
    )
    write_json(output / "code_fingerprint_comparison.json", code_fingerprint_comparison)
    if code_fingerprint_comparison["status"] != "PASS":
        raise RuntimeError(
            "driver/worker code fingerprint mismatch: "
            f"missing={code_fingerprint_comparison['missing_fingerprint_trials']}, "
            f"mismatched={code_fingerprint_comparison['mismatched_trials']}"
        )
    pd.DataFrame(trial_rows).to_parquet(output / "trial_results.parquet", index=False)
    pd.DataFrame(trial_rows).to_csv(output / "trial_results.csv", index=False)
    successful_trials = sum(
        1
        for row in trial_rows
        if row.get("status") == "PASS" or "COMPLETE" in str(row.get("status"))
    )
    trial_summary["successful_trials"] = successful_trials
    trial_summary["count_match"] = trial_summary["copied"] == successful_trials
    write_json(output / "trial_persistence.json", trial_summary)
    write_json(
        output / "selected_config.json",
        {
            "model_name": task.model_name,
            "track": task.track,
            "position": task.position,
            "source_backend": task.backend,
            "execution_backend": execution_backend,
            "config": selected_config,
        },
    )
    if config.persistence.persist_all_successful_trials and (
        trial_summary["failures"] or not trial_summary["count_match"]
    ):
        raise RuntimeError(f"trial persistence failures: {trial_summary}")

    metrics: dict[str, Any] = {}
    if actual_frame is not None:
        actual_panel = build_panel(
            actual_frame,
            contract,
            track=task.track,
            position=task.position,
        )
        actual_by_id = actual_panel.set_index("unique_id")["y"]
        predicted_by_id = prediction_before.set_index("unique_id")[point_column]
        common = [
            item
            for item in actual_by_id.index.intersection(predicted_by_id.index)
            if str(item) != "TOTAL"
        ]
        common.sort(key=str)
        actual_values = actual_by_id.loc[common].to_numpy(dtype=float)
        predicted_values = predicted_by_id.loc[common].to_numpy(dtype=float)
        metric_rows: list[dict[str, Any]] = []
        position_rows: list[dict[str, Any]] = []
        prediction_rows: list[dict[str, Any]] = []
        variants = prediction_variants(predicted_values)
        primary_variant = "rounded" if len(common) == 1 else "reconciled"
        for variant, variant_values in variants.items():
            variant_metrics = score_draw_matrix(
                actual_values.reshape(1, -1),
                variant_values.reshape(1, -1),
            )
            if len(common) == 1:
                variant_metrics["all_positions_hit_pm1"] = float("nan")
            metric_rows.append({"variant": variant, **variant_metrics})
            for unique_id, actual_value, predicted_value in zip(
                common,
                actual_values,
                variant_values,
                strict=True,
            ):
                one = score_draw_matrix(
                    np.array([[actual_value]], dtype=float),
                    np.array([[predicted_value]], dtype=float),
                )
                one["all_positions_hit_pm1"] = float("nan")
                position_rows.append(
                    {
                        "variant": variant,
                        "unique_id": str(unique_id),
                        **one,
                    }
                )
                prediction_rows.append(
                    {
                        "variant": variant,
                        "unique_id": str(unique_id),
                        "actual": float(actual_value),
                        "prediction": float(predicted_value),
                        "origin": task.origin,
                    }
                )
        metrics = next(row for row in metric_rows if row["variant"] == primary_variant)
        pd.DataFrame(metric_rows).to_parquet(
            output / "metrics_by_variant.parquet",
            index=False,
        )
        pd.DataFrame(metric_rows).to_csv(
            output / "metrics_by_variant.csv",
            index=False,
        )
        pd.DataFrame(position_rows).to_parquet(
            output / "position_metrics.parquet",
            index=False,
        )
        pd.DataFrame(position_rows).to_csv(
            output / "position_metrics.csv",
            index=False,
        )
        pd.DataFrame(prediction_rows).to_parquet(
            output / "prediction_records.parquet",
            index=False,
        )
        pd.DataFrame(prediction_rows).to_csv(
            output / "prediction_records.csv",
            index=False,
        )
        if task.track == "h_hint" and "TOTAL" in predicted_by_id.index:
            bottom_ids = [item for item in common if str(item).startswith("P")]
            total_prediction = float(predicted_by_id.loc["TOTAL"])
            bottom_sum = float(predicted_by_id.loc[bottom_ids].sum())
            metrics["hierarchy_coherence_error"] = abs(total_prediction - bottom_sum)
            metrics["hierarchy_coherent"] = bool(
                np.isclose(total_prediction, bottom_sum, rtol=1e-5, atol=1e-5)
            )
        write_json(output / "metrics.json", metrics)

    if (
        CampaignStage(task.stage) == CampaignStage.PROSPECTIVE
        and config.persistence.freeze_prospective
    ):  # noqa: E501
        freeze_path = output / "prediction_freeze.json"
        write_json(
            freeze_path,
            {
                "frozen_at": datetime.now(UTC).isoformat(),
                "actual_known": False,
                "prediction_sha256": sha256_file(bundle_target / "prediction_before_save.parquet"),
                "task": task.as_dict(),
            },
        )

    manifest = {
        "schema_version": "all-auto-task-v1",
        "status": "PASS",
        "task": task.as_dict(),
        "execution_backend": execution_backend,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "duration_seconds": time.monotonic() - started,
        "run_id": run_root.name,
        "neuralforecast_version": __import__("neuralforecast").__version__,
        "git": _git_snapshot(project_root),
        "code_sha256": _code_sha256(project_root),
        "code_fingerprint_status": code_fingerprint_comparison["status"],
        "data_sha256": sha256_file(config.data_path.resolve()),
        "trial_count": len(trial_rows),
        "trial_persistence": trial_summary,
        "load_predict": load_verify,
        "bundle": bundle_manifest,
        "metrics": metrics,
    }
    write_json(output / "manifest.json", manifest)
    write_sha256s(output)
    shutil.rmtree(trial_temp, ignore_errors=True)
    return manifest


def inventory(project_root: Path, config: CampaignConfig, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    records = discover_auto_models()
    rows = [
        record.as_dict() | {"resource_profile": resource_profile_name(record.name)}
        for record in records
    ]
    pd.DataFrame(rows).to_csv(output / "AUTO_MODEL_REGISTRY.csv", index=False)
    pd.DataFrame(rows).to_parquet(output / "AUTO_MODEL_REGISTRY.parquet", index=False)
    write_json(output / "AUTO_MODEL_REGISTRY.json", rows)
    argument_catalog = build_argument_catalog()
    signatures = runtime_signature_catalog()
    write_json(output / "ARGUMENT_COVERAGE_CATALOG.json", argument_catalog)
    argument_frame = _parquet_safe_frame(argument_catalog)
    argument_frame.to_parquet(
        output / "ARGUMENT_COVERAGE_CATALOG.parquet",
        index=False,
    )
    argument_frame.to_csv(
        output / "ARGUMENT_COVERAGE_CATALOG.csv",
        index=False,
    )
    write_json(output / "API_SIGNATURES.json", signatures)

    domain_rows: list[dict[str, Any]] = []
    config_catalog: dict[str, Any] = {}
    failures: list[dict[str, str]] = []
    for record in records:
        try:
            if record.is_hint:
                config_catalog[record.name] = {"status": "SPECIAL_AUTOHINT", "config": None}
                continue
            n_series = 5 if record.requires_n_series else None
            ray_config = get_default_config(
                record.name, h=config.h, backend="ray", n_series=n_series
            )  # noqa: E501
            descriptions = describe_config(ray_config)
            config_catalog[record.name] = {
                "status": "PASS",
                "config_repr": {key: repr(value) for key, value in ray_config.items()},
            }
            for description in descriptions:
                domain_rows.append({"model": record.name, **description.as_dict()})
        except Exception as exc:
            failures.append({"model": record.name, "error": f"{type(exc).__name__}: {exc}"})
            config_catalog[record.name] = {"status": "FAIL", "error": failures[-1]["error"]}

    write_json(output / "AUTO_DEFAULT_CONFIG_CATALOG.json", config_catalog)
    domain_frame = _parquet_safe_frame(domain_rows)
    domain_frame.to_parquet(output / "AUTO_CONFIG_DOMAINS.parquet", index=False)
    domain_frame.to_csv(output / "AUTO_CONFIG_DOMAINS.csv", index=False)
    write_json(output / "failures.json", failures)
    manifest = {
        "status": (
            "PASS"
            if not failures and all(item["status"] == "PASS" for item in signatures.values())
            else "PARTIAL"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "neuralforecast_version": __import__("neuralforecast").__version__,
        "model_count": len(records),
        "false_positive_count": 0,
        "default_config_failures": len(failures),
        "api_signature_status": (
            "PASS" if all(item["status"] == "PASS" for item in signatures.values()) else "FAIL"
        ),
        "git": _git_snapshot(project_root),
        "code_sha256": _code_sha256(project_root),
        "python": sys.version,
        "platform": platform.platform(),
        "spec_sha256": sha256_file(project_root / "docs/NEURALFORECAST_ALL_AUTO_CAMPAIGN_SPEC.md")
        if (project_root / "docs/NEURALFORECAST_ALL_AUTO_CAMPAIGN_SPEC.md").is_file()
        else None,
    }
    write_json(output / "manifest.json", manifest)
    write_sha256s(output)
    return manifest


def plan(project_root: Path, config: CampaignConfig, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    records = discover_auto_models()

    smoke_tasks = build_tasks(
        records,
        config,
        stage=CampaignStage.SMOKE,
        smoke=True,
        backends=("ray", "optuna") if config.search.optuna_smoke else ("ray",),
    )
    coverage_base = build_tasks(
        records,
        config,
        stage=CampaignStage.COVERAGE,
        smoke=False,
    )
    hpo_tasks = build_tasks(records, config, stage=CampaignStage.HPO, smoke=False)
    oof_base = build_tasks(records, config, stage=CampaignStage.OOF, smoke=False)
    holdout_base = build_tasks(
        records,
        config,
        stage=CampaignStage.HOLDOUT,
        smoke=False,
    )
    prospective_tasks = build_tasks(
        records,
        config,
        stage=CampaignStage.PROSPECTIVE,
        smoke=False,
    )

    task_rows: list[dict[str, Any]] = []
    for task in [
        *smoke_tasks,
        *coverage_base,
        *hpo_tasks,
        *oof_base,
        *holdout_base,
        *prospective_tasks,
    ]:
        task_rows.append(task.as_dict() | {"task_key": task.key})
    pd.DataFrame(task_rows).to_parquet(
        output / "CAMPAIGN_TASK_PLAN.parquet",
        index=False,
    )
    pd.DataFrame(task_rows).to_csv(output / "CAMPAIGN_TASK_PLAN.csv", index=False)

    coverage_rows: list[dict[str, Any]] = []
    coverage_reports: dict[str, Any] = {}
    coverage_counts: dict[str, int] = {}
    for record in records:
        if record.is_hint:
            coverage_counts[record.name] = 3
            coverage_reports[record.name] = {
                "coverage_rate": 1.0,
                "row_count": 3,
                "special": "AutoHINT reconciliation coverage",
            }
            continue
        n_series = 5 if record.requires_n_series else None
        default = get_default_config(
            record.name,
            h=config.h,
            backend="ray",
            n_series=n_series,
        )
        descriptions = describe_config(default)
        levels = add_random_representatives(
            descriptions,
            count=config.search.coverage_random_samples,
            seed=config.search.search_seed,
        )
        for protected in ("h", "loss", "valid_loss"):
            levels.pop(protected, None)
        rows = build_pairwise_plan(levels)
        report = coverage_report(levels, rows)
        coverage_reports[record.name] = report
        coverage_counts[record.name] = len(rows)
        for index, row in enumerate(rows):
            coverage_rows.append(
                {
                    "model": record.name,
                    "config_index": index,
                    "config_json": json.dumps(row, default=repr, sort_keys=True),
                }
            )
    pd.DataFrame(coverage_rows).to_parquet(
        output / "AUTO_CONFIG_COVERAGE_PLAN.parquet",
        index=False,
    )
    pd.DataFrame(coverage_rows).to_csv(
        output / "AUTO_CONFIG_COVERAGE_PLAN.csv",
        index=False,
    )
    write_json(output / "AUTO_CONFIG_COVERAGE_REPORT.json", coverage_reports)

    coverage_task_count = sum(coverage_counts[task.model_name] for task in coverage_base)
    stage_counts = [
        {
            "stage": CampaignStage.SMOKE.value,
            "planned_tasks": len(smoke_tasks),
            "planned_trial_models": len(smoke_tasks),
        },
        {
            "stage": CampaignStage.API_COVERAGE.value,
            "planned_tasks": len(api_case_plan()),
            "planned_trial_models": len(api_case_plan()),
        },
        {
            "stage": CampaignStage.COVERAGE.value,
            "planned_tasks": coverage_task_count,
            "planned_trial_models": coverage_task_count,
        },
        {
            "stage": CampaignStage.HPO.value,
            "planned_tasks": len(hpo_tasks),
            "planned_trial_models": len(hpo_tasks) * config.search.num_samples,
        },
        {
            "stage": CampaignStage.VALIDATE_TRIALS.value,
            "planned_tasks": (len(hpo_tasks) * config.search.num_samples),
            "planned_trial_models": (
                len(hpo_tasks) * config.search.num_samples * config.split.validation_draws
            ),
        },
        {
            "stage": CampaignStage.OOF.value,
            "planned_tasks": (
                len(oof_base) * config.split.oof_folds * config.split.oof_origins_per_fold
            ),
            "planned_trial_models": (
                len(oof_base) * config.split.oof_folds * config.split.oof_origins_per_fold
            ),
        },
        {
            "stage": CampaignStage.HOLDOUT.value,
            "planned_tasks": len(holdout_base) * config.split.holdout_draws,
            "planned_trial_models": len(holdout_base) * config.split.holdout_draws,
        },
        {
            "stage": CampaignStage.PROSPECTIVE.value,
            "planned_tasks": len(prospective_tasks),
            "planned_trial_models": len(prospective_tasks),
        },
    ]
    stage_frame = pd.DataFrame(stage_counts)
    stage_frame.to_parquet(output / "STAGE_COUNT_PLAN.parquet", index=False)
    stage_frame.to_csv(output / "STAGE_COUNT_PLAN.csv", index=False)

    manifest = {
        "status": (
            "PASS"
            if all(report["coverage_rate"] == 1.0 for report in coverage_reports.values())
            else "FAIL"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "model_count": len(records),
        "base_task_count": len(task_rows),
        "coverage_config_count": len(coverage_rows),
        "coverage_execution_task_count": coverage_task_count,
        "api_coverage_case_count": len(api_case_plan()),
        "task_count_semantics": "PRE_PROMOTION_UPPER_BOUND",
        "post_validation_promotion_applied_at_runtime": True,
        "planned_execution_tasks": int(stage_frame["planned_tasks"].sum()),
        "planned_trial_models": int(stage_frame["planned_trial_models"].sum()),
        "git": _git_snapshot(project_root),
        "code_sha256": _code_sha256(project_root),
        "data_sha256": sha256_file(config.data_path.resolve()),
    }
    write_json(output / "manifest.json", manifest)
    write_sha256s(output)
    return manifest


def _write_hpo_selected_configs(run_root: Path) -> int:
    target = run_root / "selected_configs"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for selected_path in run_root.glob("tasks/**/selected_config.json"):
        payload = json.loads(selected_path.read_text(encoding="utf-8"))
        task_manifest = json.loads(
            (selected_path.parent / "manifest.json").read_text(encoding="utf-8")
        )
        task = CampaignTask(**task_manifest["task"])
        payload["selection_basis"] = "BaseAuto_internal_validation_loss"
        write_json(target / f"{_selection_name(task)}.json", payload)
        count += 1
    return count


def _load_selected_config(source_run: Path, task: CampaignTask) -> dict[str, Any]:
    path = source_run / "selected_configs" / f"{_selection_name(task)}.json"
    if not path.is_file():
        raise FileNotFoundError(f"selected config missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = payload.get("config")
    if not isinstance(config, dict) or not config:
        raise ValueError(f"selected config invalid: {path}")
    return config


def _coverage_tasks(
    base_tasks: list[CampaignTask],
    records: list[AutoModelRecord],
    config: CampaignConfig,
) -> tuple[list[CampaignTask], dict[str, dict[str, Any]], dict[str, Any]]:
    record_map = {record.name: record for record in records}
    tasks: list[CampaignTask] = []
    fixed: dict[str, dict[str, Any]] = {}
    reports: dict[str, Any] = {}
    cache: dict[str, list[dict[str, Any]]] = {}
    for task in base_tasks:
        record = record_map[task.model_name]
        if record.is_hint:
            configs = [
                {"reconciliation": value} for value in ("BottomUp", "MinTraceOLS", "MinTraceWLS")
            ]
            report = {
                "coverage_rate": 1.0,
                "row_count": len(configs),
                "special": "AutoHINT reconciliation coverage",
            }
        else:
            if task.model_name not in cache:
                n_series = 5 if record.requires_n_series else None
                default = get_default_config(
                    task.model_name,
                    h=config.h,
                    backend="ray",
                    n_series=n_series,
                )
                descriptions = describe_config(default)
                levels = add_random_representatives(
                    descriptions,
                    count=config.search.coverage_random_samples,
                    seed=config.search.search_seed,
                )
                for protected in ("h", "loss", "valid_loss"):
                    levels.pop(protected, None)
                configs = build_pairwise_plan(levels)
                cache[task.model_name] = configs
                report = coverage_report(levels, configs)
                reports[task.model_name] = report
            configs = cache[task.model_name]
            report = reports[task.model_name]
        reports.setdefault(task.model_name, report)
        for index, config_values in enumerate(configs):
            values: dict[str, Any] = dict(config_values)
            values.update(
                {
                    "accelerator": config.resources.accelerator,
                    "devices": config.resources.devices,
                    "precision": config.resources.precision,
                    "enable_checkpointing": False,
                    "enable_progress_bar": False,
                    "logger": False,
                    "deterministic": True,
                    "benchmark": False,
                }
            )
            expanded = replace(task, config_index=index)
            tasks.append(expanded)
            fixed[expanded.key] = values
    tasks.sort(key=lambda item: item.key)
    if config.max_tasks is not None:
        tasks = tasks[: config.max_tasks]
        fixed = {task.key: fixed[task.key] for task in tasks}
    return tasks, fixed, reports


def _validation_replay_tasks(
    source_run: Path,
    frame: pd.DataFrame,
    config: CampaignConfig,
) -> tuple[list[CampaignTask], dict[str, dict[str, Any]]]:
    tasks: list[CampaignTask] = []
    fixed: dict[str, dict[str, Any]] = {}
    pre_holdout = len(frame) - config.split.holdout_draws
    validation_start = pre_holdout - config.split.validation_draws
    origins = range(validation_start, pre_holdout)
    for source_manifest_path in sorted(source_run.glob("tasks/**/manifest.json")):
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        source_task = CampaignTask(**source_manifest["task"])
        trial_root = source_manifest_path.parent / "trials"
        successful_trial_dirs = [
            trial_dir
            for trial_dir in sorted(trial_root.glob("trial_*"))
            if (trial_dir / "config.json").is_file() and (trial_dir / "model.ckpt").is_file()
        ]
        for config_index, trial_dir in enumerate(successful_trial_dirs):
            config_path = trial_dir / "config.json"
            trial_config = json.loads(config_path.read_text(encoding="utf-8"))
            for origin in origins:
                task = CampaignTask(
                    stage=CampaignStage.VALIDATE_TRIALS.value,
                    model_name=source_task.model_name,
                    track=source_task.track,
                    position=source_task.position,
                    seed=source_task.seed,
                    origin=origin,
                    backend=source_task.backend,
                    config_index=config_index,
                )
                tasks.append(task)
                fixed[task.key] = trial_config
    tasks.sort(key=lambda item: item.key)
    if config.max_tasks is not None:
        tasks = tasks[: config.max_tasks]
        fixed = {task.key: fixed[task.key] for task in tasks}
    return tasks, fixed


def _select_replayed_configs(run_root: Path) -> int:
    rows: list[dict[str, Any]] = []
    configs: dict[tuple[str, str, int | None, int], dict[str, Any]] = {}
    for manifest_path in run_root.glob("tasks/**/manifest.json"):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        task = CampaignTask(**payload["task"])
        metrics = payload.get("metrics") or {}
        if task.config_index is None or not metrics:
            continue
        selected_path = manifest_path.parent / "selected_config.json"
        selected_payload = json.loads(selected_path.read_text(encoding="utf-8"))
        key = (task.model_name, task.track, task.position, task.config_index)
        configs[key] = selected_payload["config"]
        rows.append(
            {
                "model_name": task.model_name,
                "track": task.track,
                "position": task.position,
                "config_index": task.config_index,
                "origin": task.origin,
                **metrics,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return 0
    summary = (
        frame.groupby(
            ["model_name", "track", "position", "config_index"],
            dropna=False,
        )
        .agg(
            hit_pm1=("hit_pm1", "mean"),
            all_positions_hit_pm1=("all_positions_hit_pm1", "mean"),
            mae=("mae", "mean"),
            mse=("mse", "mean"),
            rmse=("rmse", "mean"),
            origins=("origin", "nunique"),
        )
        .reset_index()
    )
    summary.to_parquet(run_root / "validation_trial_metrics.parquet", index=False)
    summary.to_csv(run_root / "validation_trial_metrics.csv", index=False)
    target = run_root / "selected_configs"
    target.mkdir(parents=True, exist_ok=True)
    selected_count = 0
    for (model, track, position), group in summary.groupby(
        ["model_name", "track", "position"], dropna=False
    ):
        ranked = group.sort_values(
            ["hit_pm1", "all_positions_hit_pm1", "mae", "rmse", "config_index"],
            ascending=[False, False, True, True, True],
            kind="stable",
        )
        best = ranked.iloc[0]
        position_value = None if pd.isna(position) else int(position)
        config_key = (str(model), str(track), position_value, int(best["config_index"]))
        task = CampaignTask(
            stage=CampaignStage.VALIDATE_TRIALS.value,
            model_name=str(model),
            track=str(track),
            position=position_value,
            seed=0,
        )
        write_json(
            target / f"{_selection_name(task)}.json",
            {
                "selection_basis": "validation_hit_pm1",
                "model_name": model,
                "track": track,
                "position": position_value,
                "config_index": int(best["config_index"]),
                "metrics": _jsonable(best.to_dict()),
                "config": configs[config_key],
            },
        )
        selected_count += 1
    return selected_count


def _is_oom_error(exc: BaseException) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "cuda out of memory",
        "outofmemoryerror",
        "cublas_status_alloc_failed",
        "failed to allocate",
    )
    return any(marker in message for marker in markers)


def _attempt_config(config: CampaignConfig, attempt: int) -> CampaignConfig:
    if attempt <= 0 or config.resources.gpus_per_trial <= 0:
        return config
    gpu_fraction = min(
        1.0,
        config.resources.gpus_per_trial * (2**attempt),
    )
    resources = config.resources.model_copy(
        update={
            "gpus_per_trial": gpu_fraction,
            "gpu_concurrency": max(1, int(1.0 / gpu_fraction)),
        }
    )
    return config.model_copy(update={"resources": resources})


def _archive_failed_attempt(
    run_root: Path,
    task: CampaignTask,
    attempt: int,
) -> None:
    archive = run_root / "failed_attempts" / Path(task.key) / f"attempt_{attempt:02d}"
    archive.mkdir(parents=True, exist_ok=True)
    output = _task_output(run_root, task)
    trial_work = run_root / "trial_work" / Path(task.key)
    if output.exists():
        target = archive / "task_output"
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(output), str(target))
    if trial_work.exists():
        target = archive / "trial_work"
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(trial_work), str(target))


def run_task_with_retry(
    *,
    project_root: Path,
    run_root: Path,
    frame: pd.DataFrame,
    contract: Any,
    config: CampaignConfig,
    task: CampaignTask,
    num_samples: int,
    smoke: bool,
    fixed_config: dict[str, Any] | None,
    backend_override: str | None = None,
) -> dict[str, Any]:
    task_output = _task_output(run_root, task)
    task_manifest_path = task_output / "manifest.json"
    if task_output.exists() and not task_manifest_path.is_file():
        _archive_failed_attempt(run_root, task, 0)

    profiled_config = apply_model_resource_profile(config, task.model_name)
    attempt_errors: list[dict[str, Any]] = []
    for attempt in range(profiled_config.resources.max_retries + 1):
        attempt_config = _attempt_config(profiled_config, attempt)
        try:
            manifest = execute_task(
                project_root=project_root,
                run_root=run_root,
                frame=frame,
                contract=contract,
                config=attempt_config,
                task=task,
                num_samples=num_samples,
                smoke=smoke,
                fixed_config=fixed_config,
                backend_override=backend_override,
            )
            manifest["attempt"] = attempt
            manifest["resource_profile"] = resource_profile_name(task.model_name)
            manifest["resource_retry"] = {
                "gpus_per_trial": attempt_config.resources.gpus_per_trial,
                "cpus_per_trial": attempt_config.resources.cpus_per_trial,
            }
            return {"ok": True, "manifest": manifest}
        except Exception as exc:
            attempt_failure = {
                "attempt": attempt,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "is_oom": _is_oom_error(exc),
                "gpus_per_trial": attempt_config.resources.gpus_per_trial,
                "traceback": traceback.format_exc(),
            }
            attempt_errors.append(attempt_failure)
            write_json(
                run_root / "attempt_failures" / Path(task.key) / f"attempt_{attempt:02d}.json",
                attempt_failure,
            )
            retryable = (
                attempt_failure["is_oom"] and attempt < profiled_config.resources.max_retries
            )
            _archive_failed_attempt(run_root, task, attempt)
            if retryable:
                continue
            failure = {
                "task": task.as_dict(),
                "attempts": attempt_errors,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": attempt_failure["traceback"],
            }
            write_json(
                _task_output(run_root, task).with_suffix(".failed.json"),
                failure,
            )
            return {"ok": False, "failure": failure}
    raise AssertionError("retry loop terminated unexpectedly")


def run_stage(
    project_root: Path,
    config: CampaignConfig,
    run_root: Path,
    stage: CampaignStage,
    *,
    source_run: Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    if run_root.exists() and not resume:
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True, exist_ok=resume)
    frame, contract = load_miniloto(config)
    write_json(run_root / "data_contract.json", contract.as_dict())
    write_json(run_root / "campaign_config.json", config.model_dump(mode="json"))
    records = discover_auto_models()
    smoke = stage == CampaignStage.SMOKE
    backends = (
        ("ray", "optuna") if smoke and config.search.optuna_smoke else (config.search.backend,)
    )
    fixed_configs: dict[str, dict[str, Any]] = {}
    coverage_reports: dict[str, Any] = {}

    if stage == CampaignStage.VALIDATE_TRIALS:
        if source_run is None:
            raise ValueError("validate-trials requires --source-run pointing to an HPO run")
        tasks, fixed_configs = _validation_replay_tasks(source_run, frame, config)
    else:
        tasks = build_tasks(records, config, stage=stage, smoke=smoke, backends=backends)

    if stage == CampaignStage.COVERAGE:
        tasks, fixed_configs, coverage_reports = _coverage_tasks(tasks, records, config)
        write_json(run_root / "AUTO_CONFIG_COVERAGE_REPORT.json", coverage_reports)
    elif stage == CampaignStage.HOLDOUT:
        if source_run is None:
            raise ValueError("holdout requires --source-run with Hit@±1-selected configs")
        tasks = [
            replace(task, origin=origin)
            for task in tasks
            for origin in holdout_origins(frame, config)
        ]
    elif stage == CampaignStage.OOF:
        if source_run is None:
            raise ValueError("oof requires --source-run with Hit@±1-selected configs")
        tasks = [
            replace(task, fold=fold, origin=origin)
            for task in tasks
            for fold, origin in oof_origins(frame, config)
        ]
    elif stage == CampaignStage.PROSPECTIVE and source_run is None:
        raise ValueError("prospective requires --source-run with Hit@±1-selected configs")

    if source_run is not None and stage in {
        CampaignStage.OOF,
        CampaignStage.HOLDOUT,
        CampaignStage.PROSPECTIVE,
    }:
        tasks = filter_tasks_by_promotion(tasks, source_run)

    tasks.sort(key=lambda item: item.key)
    if config.max_tasks is not None and stage not in {
        CampaignStage.COVERAGE,
        CampaignStage.VALIDATE_TRIALS,
    }:
        tasks = tasks[: config.max_tasks]

    pd.DataFrame([task.as_dict() | {"task_key": task.key} for task in tasks]).to_parquet(
        run_root / "task_plan.parquet", index=False
    )
    write_json(
        run_root / "plan_manifest.json",
        {"stage": stage.value, "task_count": len(tasks)},
    )
    if source_run is not None and stage in {
        CampaignStage.OOF,
        CampaignStage.HOLDOUT,
        CampaignStage.PROSPECTIVE,
    }:
        for task in tasks:
            fixed_configs[task.key] = _load_selected_config(source_run, task)

    failures: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []

    def update_progress(current: str | None) -> None:
        write_json(
            run_root / "progress.json",
            {
                "stage": stage.value,
                "completed": len(completed),
                "failed": len(failures),
                "total": len(tasks),
                "current": current,
            },
        )

    def record_result(task: CampaignTask, result: dict[str, Any]) -> None:
        if result.get("ok"):
            completed.append(result["manifest"])
        else:
            failures.append(result["failure"])
        update_progress(None)

    update_progress(None)
    fixed_parallel_stages = {
        CampaignStage.COVERAGE,
        CampaignStage.VALIDATE_TRIALS,
        CampaignStage.OOF,
        CampaignStage.HOLDOUT,
        CampaignStage.PROSPECTIVE,
    }
    parallel_enabled = config.resources.parallel_fixed_tasks and stage in fixed_parallel_stages
    parallel_tasks = (
        [task for task in tasks if task.model_name != "AutoHINT"] if parallel_enabled else []
    )
    sequential_tasks = (
        [task for task in tasks if task.model_name == "AutoHINT"] if parallel_enabled else tasks
    )

    if parallel_tasks:
        from .scheduler import run_parallel_fixed_tasks

        run_parallel_fixed_tasks(
            project_root=project_root,
            run_root=run_root,
            frame=frame,
            contract=contract,
            config=config,
            tasks=parallel_tasks,
            fixed_configs=fixed_configs,
            num_samples=1,
            smoke=smoke,
            on_result=record_result,
        )

    for task in sequential_tasks:
        update_progress(task.key)
        result = run_task_with_retry(
            project_root=project_root,
            run_root=run_root,
            frame=frame,
            contract=contract,
            config=config,
            task=task,
            num_samples=(
                1
                if stage
                in {
                    CampaignStage.SMOKE,
                    CampaignStage.COVERAGE,
                    CampaignStage.VALIDATE_TRIALS,
                    CampaignStage.OOF,
                    CampaignStage.HOLDOUT,
                    CampaignStage.PROSPECTIVE,
                }
                else config.search.num_samples
            ),
            smoke=smoke,
            fixed_config=fixed_configs.get(task.key),
        )
        record_result(task, result)

    selected_config_count = 0
    if stage == CampaignStage.HPO:
        selected_config_count = _write_hpo_selected_configs(run_root)
    elif stage == CampaignStage.VALIDATE_TRIALS:
        selected_config_count = _select_replayed_configs(run_root)

    metric_summary = summarize_metrics(run_root)
    comparison_scope = {
        "included_model_family": "NeuralForecast AutoModel",
        "baseline_models_included": False,
        "baseline_execution_enabled": False,
        "ranking_scope": "auto_models_only",
        "reason": (
            "Baseline methods were excluded by project requirement because "
            "they produce fixed, repeated, naive or simple statistical values "
            "and are not part of the formal AutoModel comparison."
        ),
    }

    write_json(run_root / "failures.json", failures)
    manifest = {
        "schema_version": "all-auto-campaign-run-v1",
        "status": "PASS" if not failures and len(completed) == len(tasks) else "PARTIAL",
        "stage": stage.value,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_tasks": len(completed),
        "failed_tasks": len(failures),
        "planned_tasks": len(tasks),
        "selected_config_count": selected_config_count,
        "metric_summary": metric_summary,
        "comparison_scope": comparison_scope,
        "git": _git_snapshot(project_root),
        "code_sha256": _code_sha256(project_root),
        "data_sha256": sha256_file(config.data_path.resolve()),
        "run_id": run_root.name,
        "neuralforecast_version": __import__("neuralforecast").__version__,
        "api_coverage_status": "PARTIAL_API_COVERAGE",
        "api_coverage_note": "distributed_config Spark track is not part of local GPU stages",
    }
    write_json(run_root / "manifest.json", manifest)
    write_sha256s(run_root)
    return manifest


def verify_run(run_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file():
        failures.append("manifest.json missing")
        manifest: dict[str, Any] = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    failures.extend(verify_sha256s(run_root))
    # `manifest.json` also appears nested inside each task's `best_model/` bundle
    # and inside `trials/trial_*/`; those are bundle/trial manifests, not task
    # manifests, and lack a `trial_persistence` key, so counting them here would
    # both inflate the task count and manufacture false "trial count mismatch"
    # failures against tasks that never claimed to have that key.
    task_manifests = [
        path
        for path in run_root.glob("tasks/**/manifest.json")
        if "best_model" not in path.relative_to(run_root).parts
        and "trials" not in path.relative_to(run_root).parts
    ]
    passed_tasks = 0
    for task_manifest in task_manifests:
        payload = json.loads(task_manifest.read_text(encoding="utf-8"))
        if payload.get("status") != "PASS":
            failures.append(f"task not PASS: {task_manifest}")
            continue
        passed_tasks += 1
        persistence = payload.get("trial_persistence") or {}
        if persistence.get("count_match") is not True:
            failures.append(f"trial count mismatch: {task_manifest}")
        if persistence.get("failures"):
            failures.append(f"trial persistence failure: {task_manifest}")

    required_bundle_files = {
        "requested_config.json",
        "effective_config.json",
        "config_diff.json",
        "base_auto_args.json",
        "neuralforecast_args.json",
        "fit_args.json",
        "state_dict.pt",
        "train_panel.parquet",
        "prediction_before_save.parquet",
        "prediction_after_load.parquet",
        "parameter_statistics.parquet",
        "model_structure.txt",
        "runtime.json",
        "gpu_pid.json",
        "load_predict_verification.json",
        "manifest.json",
        "SHA256SUMS",
    }
    for verification in run_root.glob("tasks/**/best_model/load_predict_verification.json"):
        payload = json.loads(verification.read_text(encoding="utf-8"))
        if payload.get("status") != "PASS":
            failures.append(f"load verification failed: {verification}")
        if payload.get("cpu_fallback"):
            failures.append(f"cpu fallback: {verification}")
        if payload.get("prediction_match") is not True:
            failures.append(f"prediction mismatch: {verification}")
        if payload.get("finite") is not True:
            failures.append(f"non-finite prediction: {verification}")
        if payload.get("gpu_pid", {}).get("gpu_pid_verified") is not True:
            failures.append(f"GPU PID not verified: {verification}")

    for bundle in run_root.glob("tasks/**/best_model"):
        if bundle.is_dir():
            present = {path.name for path in bundle.iterdir() if path.is_file()}
            for missing in sorted(required_bundle_files - present):
                failures.append(f"bundle missing {missing}: {bundle}")
            config_diff_path = bundle / "config_diff.json"
            if config_diff_path.is_file():
                config_diff = json.loads(config_diff_path.read_text(encoding="utf-8"))
                if config_diff.get("status") != "PASS":
                    failures.append(f"bundle config mismatch: {bundle}")
            for failure in verify_sha256s(bundle):
                failures.append(f"bundle:{bundle}:{failure}")

    for trial in run_root.glob("tasks/**/trials/trial_*"):
        if not trial.is_dir() or trial.name.endswith(".partial"):
            continue
        trial_manifest = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))
        for failure in verify_sha256s(trial):
            failures.append(f"trial:{trial}:{failure}")
        if trial_manifest.get("status") == "PASS":
            required_trial_files = {
                "model.ckpt",
                "state_dict.pt",
                "requested_config.json",
                "effective_config.json",
                "config_diff.json",
                "parameter_statistics.parquet",
                "trial_metrics.parquet",
                "prediction_before_save.parquet",
                "prediction_after_load.parquet",
                "runtime.json",
                "gpu_pid.json",
                "load_predict_verification.json",
                "manifest.json",
                "SHA256SUMS",
            }
            present = {path.name for path in trial.iterdir() if path.is_file()}
            for missing in sorted(required_trial_files - present):
                failures.append(f"trial missing {missing}: {trial}")
            verification_path = trial / "load_predict_verification.json"
            if not verification_path.is_file():
                failures.append(f"trial verification missing: {trial}")
                continue
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            if verification.get("status") != "PASS":
                failures.append(f"trial verification failed: {trial}")
            if verification.get("cpu_fallback"):
                failures.append(f"trial CPU fallback: {trial}")
            if verification.get("gpu_pid", {}).get("gpu_pid_verified") is not True:
                failures.append(f"trial GPU PID not verified: {trial}")
            if trial_manifest.get("state_dict_finite") is not True:
                failures.append(f"trial state_dict not finite: {trial}")
            if trial_manifest.get("config_status") != "PASS":
                failures.append(f"trial config mismatch: {trial}")

    planned = int(manifest.get("planned_tasks", 0) or 0)
    if planned and passed_tasks != planned:
        failures.append(f"task count mismatch: passed={passed_tasks}, planned={planned}")

    result = {
        "status": ("PASS" if not failures and manifest.get("status") == "PASS" else "FAIL"),
        "run_manifest_status": manifest.get("status"),
        "planned_tasks": planned,
        "passed_tasks": passed_tasks,
        "failures": failures,
    }
    write_json(run_root / "VERIFICATION_REPORT.json", result)
    # The report is part of the immutable run, so regenerate the top-level digest
    # only after it has been written.
    write_sha256s(run_root)
    return result
