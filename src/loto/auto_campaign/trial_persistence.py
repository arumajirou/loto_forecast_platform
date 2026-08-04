from __future__ import annotations

import json
import os
import shutil
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.auto_campaign.p1_compat import (
    install_p1_runtime_compatibility,
    load_trial_checkpoint_for_verification,
    save_trial_checkpoint,
)

install_p1_runtime_compatibility()


_CLASS_CACHE: dict[type, type] = {}


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, default=repr, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _commit_trial_directory(partial: Path, target: Path) -> None:
    from .persistence import write_sha256s

    write_sha256s(partial)
    if target.exists():
        shutil.rmtree(target)
    os.replace(partial, target)


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


def _effective_hparams(model: Any) -> dict[str, Any]:
    def values(inner: Any) -> dict[str, Any]:
        hparams = getattr(inner, "hparams", None)
        if hparams is None:
            return {}
        try:
            return dict(hparams)
        except Exception:
            return {key: getattr(hparams, key) for key in dir(hparams) if not key.startswith("_")}

    output = values(model)
    wrapped = getattr(model, "model", None)
    if wrapped is not None and wrapped is not model:
        output = {**values(wrapped), **output}
        output["wrapped_model_class"] = type(wrapped).__name__
    return _jsonable(output)


def _normalized_effective_value(
    key: str,
    requested_value: Any,
    requested: dict[str, Any],
    model: Any,
) -> Any | None:
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
    model: Any,
) -> dict[str, Any]:
    ignored = {
        "callbacks",
        "logger",
        "enable_progress_bar",
        "enable_checkpointing",
    }
    failures: list[str] = []
    items: dict[str, Any] = {}
    for key, requested_value in sorted(requested.items()):
        if key in ignored:
            continue
        effective_value = effective.get(key)
        if key not in effective:
            status = "NOT_EXPOSED"
            failures.append(key)
        elif isinstance(requested_value, (int, float)) and isinstance(
            effective_value, (int, float)
        ):
            status = (
                "MATCH"
                if np.isclose(
                    float(requested_value),
                    float(effective_value),
                    rtol=1e-8,
                    atol=1e-10,
                )
                else "MISMATCH"
            )
            if status != "MATCH":
                failures.append(key)
        else:
            direct_match = requested_value == effective_value or repr(requested_value) == repr(
                effective_value
            )
            if direct_match:
                status = "MATCH"
            else:
                normalized = _normalized_effective_value(
                    key,
                    requested_value,
                    requested,
                    model,
                )
                if normalized is not None and (
                    normalized == effective_value or repr(normalized) == repr(effective_value)
                ):
                    status = "NORMALIZED_BY_MODEL"
                else:
                    status = "MISMATCH"
                    failures.append(key)
        items[key] = {
            "requested": _jsonable(requested_value),
            "effective": _jsonable(effective_value),
            "status": status,
        }
    return {
        "status": "PASS" if not failures else "FAIL",
        "strict_failure_count": len(failures),
        "strict_failures": failures,
        "items": items,
    }


def _write_trial_model_artifacts(
    *,
    model: Any,
    directory: Path,
    requested_config: dict[str, Any],
    metrics: dict[str, float],
    val_size: int,
    test_size: int,
    dataset: Any,
) -> dict[str, Any]:

    state = {name: value.detach().cpu() for name, value in model.state_dict().items()}
    save_trial_checkpoint(
        model=model, checkpoint_path=directory / "state_dict.pt", fallback_payload=state
    )
    rows: list[dict[str, Any]] = []
    finite = True
    for name, value in state.items():
        array = value.numpy()
        item_finite = bool(np.isfinite(array).all())
        finite = finite and item_finite
        rows.append(
            {
                "name": name,
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "numel": int(array.size),
                "finite": item_finite,
                "mean": float(array.mean()) if array.size else None,
                "std": float(array.std()) if array.size else None,
                "min": float(array.min()) if array.size else None,
                "max": float(array.max()) if array.size else None,
            }
        )
    if not finite:
        raise RuntimeError("non-finite Trial state_dict")
    pd.DataFrame(rows).to_parquet(
        directory / "parameter_statistics.parquet",
        index=False,
    )
    pd.DataFrame([metrics]).to_parquet(
        directory / "trial_metrics.parquet",
        index=False,
    )
    pd.DataFrame([metrics]).to_csv(
        directory / "trial_metrics.csv",
        index=False,
    )
    (directory / "model_structure.txt").write_text(
        repr(model) + "\n",
        encoding="utf-8",
    )
    effective = _effective_hparams(model)
    comparison = _config_diff(
        requested_config,
        effective,
        model=model,
    )
    _json_dump(directory / "requested_config.json", requested_config)
    _json_dump(directory / "effective_config.json", effective)
    _json_dump(directory / "config_diff.json", comparison)
    _json_dump(
        directory / "train_contract.json",
        {
            "val_size": val_size,
            "test_size": test_size,
            "dataset_groups": getattr(dataset, "n_groups", None),
            "dataset_min_size": getattr(dataset, "min_size", None),
            "dataset_max_size": getattr(dataset, "max_size", None),
        },
    )
    if comparison["status"] != "PASS":
        raise RuntimeError(
            f"Trial effective configuration mismatch: {comparison['strict_failures']}"
        )
    return {
        "state_dict_finite": finite,
        "config_status": comparison["status"],
    }


def _trial_load_predict_verification(
    *,
    model: Any,
    checkpoint_path: Path,
    dataset: Any,
) -> dict[str, Any]:
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    prediction_before = np.asarray(
        model.predict(dataset=dataset, step_size=1),
        dtype=float,
    )
    loaded = load_trial_checkpoint_for_verification(model=model, checkpoint_path=checkpoint_path)
    prediction_after = np.asarray(
        loaded.predict(dataset=dataset, step_size=1),
        dtype=float,
    )
    from .runtime import gpu_process_snapshot, torch_runtime_snapshot

    runtime = torch_runtime_snapshot(loaded)
    gpu_pid = gpu_process_snapshot()
    root_device = runtime.get("trainer_root_device")
    finite = bool(np.isfinite(prediction_before).all() and np.isfinite(prediction_after).all())
    shape_match = prediction_before.shape == prediction_after.shape
    prediction_match = bool(
        shape_match
        and np.allclose(
            prediction_before,
            prediction_after,
            rtol=1e-6,
            atol=1e-6,
        )
    )
    cuda_evidence = bool(
        str(root_device).startswith("cuda")
        or runtime.get("cuda_peak_memory_allocated", 0) > 0
        or gpu_pid.get("gpu_pid_verified")
    )
    result = {
        "loaded": True,
        "predicted": True,
        "finite": finite,
        "shape_match": shape_match,
        "prediction_match": prediction_match,
        "max_abs_diff": (
            float(np.max(np.abs(prediction_before - prediction_after)))
            if shape_match and prediction_before.size
            else None
        ),
        "prediction_shape": list(prediction_after.shape),
        "trainer_root_device": None if root_device is None else str(root_device),
        "runtime": runtime,
        "gpu_pid": gpu_pid,
        "cuda_execution_evidence": cuda_evidence,
        "cpu_fallback": not cuda_evidence,
    }
    result["status"] = (
        "PASS" if finite and shape_match and prediction_match and cuda_evidence else "FAIL"
    )
    np.save(checkpoint_path.parent / "prediction_before.npy", prediction_before)
    np.save(checkpoint_path.parent / "prediction_after.npy", prediction_after)
    pd.DataFrame(
        {
            "flat_index": np.arange(prediction_before.size, dtype=np.int64),
            "value": prediction_before.reshape(-1),
        }
    ).to_parquet(
        checkpoint_path.parent / "prediction_before_save.parquet",
        index=False,
    )
    pd.DataFrame(
        {
            "flat_index": np.arange(prediction_after.size, dtype=np.int64),
            "value": prediction_after.reshape(-1),
        }
    ).to_parquet(
        checkpoint_path.parent / "prediction_after_load.parquet",
        index=False,
    )
    if result["status"] != "PASS":
        raise RuntimeError(f"trial load/predict verification failed: {result}")
    return result


def _validation_diagnostics(model: Any) -> dict[str, Any]:
    """Collect every diagnostic about validation-metric reporting we can honestly obtain.

    NeuralForecast's `_fit()` (both local and distributed paths) pops
    `model._trainer` immediately after `trainer.fit()` returns, so by the time
    this mixin runs, `trainer.logged_metrics`/`trainer.progress_bar_metrics`
    no longer exist anywhere -- the trainer object itself is gone. Only
    `model.metrics` (a copy of `trainer.callback_metrics` captured by the
    library just before the pop) survives. Report that limitation explicitly
    instead of fabricating the missing fields.
    """
    metrics = dict(getattr(model, "metrics", {}) or {})
    valid_trajectories = list(getattr(model, "valid_trajectories", []) or [])
    val_size = int(getattr(model, "val_size", 0) or 0)
    return {
        "available_metric_keys": sorted(metrics),
        "configured_val_monitor": getattr(model, "val_monitor", "ptl/val_loss"),
        "callback_metrics_keys": sorted(metrics),
        "logged_metrics_keys": None,
        "progress_bar_metrics_keys": None,
        "trainer_unavailable_reason": (
            "neuralforecast.common._base_model pops model._trainer immediately "
            "after trainer.fit() returns (local and distributed fit paths alike); "
            "trainer.logged_metrics/trainer.progress_bar_metrics are therefore "
            "structurally unobtainable once _fit_model() has returned control here. "
            "Only trainer.callback_metrics survives, via model.metrics."
        ),
        "val_size": val_size,
        "validation_epoch_count": len(valid_trajectories),
        "validation_executed": bool(valid_trajectories) and val_size != 0,
    }


def _select_validation_metric(model: Any) -> tuple[str, float, dict[str, Any]]:
    """Resolve the actually-reported validation metric for `model.val_monitor`.

    Raises RuntimeError (never substitutes 0.0/NaN or falls back to train_loss)
    if the configured monitor key is absent from the metrics NeuralForecast
    actually logged.
    """
    metrics = dict(getattr(model, "metrics", {}) or {})
    configured_monitor = getattr(model, "val_monitor", "ptl/val_loss")
    diagnostics = _validation_diagnostics(model)
    if configured_monitor not in metrics:
        raise RuntimeError(
            "Validation metric was not reported: "
            f"configured={configured_monitor!r}, "
            f"available={sorted(metrics)!r}"
        )
    value = float(metrics[configured_monitor])
    diagnostics["selected_validation_metric_key"] = configured_monitor
    diagnostics["selected_validation_metric_value"] = value
    return configured_monitor, value, diagnostics


class PersistentTrialMixin:
    """Persist every successful BaseAuto trial before the backend can clean it up.

    NeuralForecast 3.2.0 reports Ray trial metrics but does not attach a model
    checkpoint. This mixin keeps the public AutoModel API and replaces only the
    two backend-specific optimization internals.
    """

    trial_artifact_root: str | None = None

    def _trial_root(self) -> Path:
        value = self.trial_artifact_root
        if not value:
            raise RuntimeError("trial_artifact_root is not configured")
        root = Path(value).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _train_tune(self, config_step, cls_model, dataset, val_size, test_size):
        from ray import tune
        from ray.tune import Checkpoint
        from ray.tune.integration.pytorch_lightning import TuneReportCallback

        metrics_map = {"loss": "ptl/val_loss", "train_loss": "train_loss"}
        callbacks = [TuneReportCallback(metrics_map, on="validation_end")]
        if "callbacks" in config_step:
            callbacks.extend(config_step["callbacks"])
        config_step = {**config_step, "callbacks": callbacks}
        for key in ("batch_size", "windows_batch_size"):
            if key in config_step:
                config_step[key] = int(config_step[key])

        persisted_config = {
            key: value
            for key, value in config_step.items()
            if key not in {"h", "loss", "valid_loss", "callbacks"}
        }
        model = self._fit_model(
            cls_model=cls_model,
            config=config_step,
            dataset=dataset,
            val_size=val_size,
            test_size=test_size,
        )
        metrics = getattr(model, "metrics", {})
        _selected_key, selected_value, validation_diagnostics = _select_validation_metric(model)
        reported = {
            "loss": selected_value,
            "train_loss": float(metrics.get("train_loss", float("nan"))),
        }
        context = tune.get_context()
        trial_id = context.get_trial_id() or "unknown"
        target = self._trial_root() / f"trial_{trial_id}"
        partial = target.with_name(target.name + ".partial")
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(parents=True, exist_ok=False)

        model.save(str(partial / "model.ckpt"))
        artifact_status = _write_trial_model_artifacts(
            model=model,
            directory=partial,
            requested_config=persisted_config,
            metrics=reported,
            val_size=val_size,
            test_size=test_size,
            dataset=dataset,
        )
        verification = _trial_load_predict_verification(
            model=model,
            checkpoint_path=partial / "model.ckpt",
            dataset=dataset,
        )
        from .runtime import code_environment_fingerprint

        _json_dump(partial / "worker_code_fingerprint.json", code_environment_fingerprint())
        _json_dump(partial / "load_predict_verification.json", verification)
        _json_dump(partial / "runtime.json", verification["runtime"])
        _json_dump(partial / "gpu_pid.json", verification["gpu_pid"])
        _json_dump(partial / "config.json", persisted_config)
        _json_dump(partial / "metrics.json", reported)
        _json_dump(partial / "validation_diagnostics.json", validation_diagnostics)
        _json_dump(
            partial / "manifest.json",
            {
                "status": "PASS",
                "backend": "ray",
                "trial_id": trial_id,
                "checkpoint": "model.ckpt",
                "validation_metric_key": validation_diagnostics["selected_validation_metric_key"],
                "validation_metric_value": validation_diagnostics[
                    "selected_validation_metric_value"
                ],
                **artifact_status,
                "load_predict_status": verification["status"],
            },
        )
        _commit_trial_directory(partial, target)
        tune.report(reported, checkpoint=Checkpoint.from_directory(target))

    def _optuna_tune_model(
        self,
        cls_model,
        dataset,
        val_size,
        test_size,
        verbose,
        num_samples,
        search_alg,
        config,
        distributed_config,
        time_budget,
    ):
        import optuna

        root = self._trial_root()

        def objective(trial):
            target = root / f"trial_{trial.number:05d}"
            partial = target.with_name(target.name + ".partial")
            if partial.exists():
                shutil.rmtree(partial)
            partial.mkdir(parents=True, exist_ok=False)
            try:
                user_cfg = config(trial)
                cfg = deepcopy(user_cfg)
                model = self._fit_model(
                    cls_model=cls_model,
                    config=cfg,
                    dataset=dataset,
                    val_size=val_size,
                    test_size=test_size,
                    distributed_config=distributed_config,
                )
                metrics = model.metrics
                _selected_key, selected_value, validation_diagnostics = _select_validation_metric(
                    model
                )
                persisted = {
                    key: value
                    for key, value in user_cfg.items()
                    if key not in {"loss", "valid_loss"}
                }
                trial.set_user_attr("ALL_PARAMS", persisted)
                trial.set_user_attr(
                    "METRICS",
                    {
                        "loss": selected_value,
                        "train_loss": float(metrics.get("train_loss", float("nan"))),
                    },
                )
                model.save(str(partial / "model.ckpt"))
                artifact_status = _write_trial_model_artifacts(
                    model=model,
                    directory=partial,
                    requested_config=persisted,
                    metrics=trial.user_attrs["METRICS"],
                    val_size=val_size,
                    test_size=test_size,
                    dataset=dataset,
                )
                verification = _trial_load_predict_verification(
                    model=model,
                    checkpoint_path=partial / "model.ckpt",
                    dataset=dataset,
                )
                from .runtime import code_environment_fingerprint

                _json_dump(partial / "worker_code_fingerprint.json", code_environment_fingerprint())
                _json_dump(
                    partial / "load_predict_verification.json",
                    verification,
                )
                _json_dump(partial / "runtime.json", verification["runtime"])
                _json_dump(partial / "gpu_pid.json", verification["gpu_pid"])
                _json_dump(partial / "config.json", persisted)
                _json_dump(partial / "metrics.json", trial.user_attrs["METRICS"])
                _json_dump(partial / "validation_diagnostics.json", validation_diagnostics)
                _json_dump(
                    partial / "manifest.json",
                    {
                        "status": "PASS",
                        "backend": "optuna",
                        "trial_number": trial.number,
                        "checkpoint": "model.ckpt",
                        "validation_metric_key": validation_diagnostics[
                            "selected_validation_metric_key"
                        ],
                        "validation_metric_value": validation_diagnostics[
                            "selected_validation_metric_value"
                        ],
                        **artifact_status,
                        "load_predict_status": verification["status"],
                    },
                )
                _commit_trial_directory(partial, target)
                return trial.user_attrs["METRICS"]["loss"]
            except Exception as exc:
                _json_dump(
                    partial / "manifest.json",
                    {
                        "status": "FAIL",
                        "backend": "optuna",
                        "trial_number": trial.number,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
                _commit_trial_directory(partial, target)
                raise

        sampler = search_alg if isinstance(search_alg, optuna.samplers.BaseSampler) else None
        create_kwargs = {"sampler": sampler, "direction": "minimize"}
        options = getattr(self, "optuna_options", None)
        if options is not None and options.create_study_kwargs is not None:
            create_kwargs.update(options.create_study_kwargs)
        study = optuna.create_study(**create_kwargs)
        optimize_kwargs = {
            "n_trials": num_samples,
            "show_progress_bar": verbose,
            "callbacks": self.callbacks,
            "timeout": time_budget,
            "catch": (Exception,),
        }
        if options is not None and options.study_kwargs is not None:
            optimize_kwargs.update(options.study_kwargs)
        study.optimize(objective, **optimize_kwargs)
        return study


def persistent_auto_class(auto_cls: type) -> type:
    """Return a stable, pickle-addressable persistent subclass."""

    cached = _CLASS_CACHE.get(auto_cls)
    if cached is not None:
        return cached
    name = f"Persistent{auto_cls.__name__}"
    created = type(
        name,
        (PersistentTrialMixin, auto_cls),
        {"__module__": __name__, "__qualname__": name},
    )
    globals()[name] = created
    _CLASS_CACHE[auto_cls] = created
    return created


def _register_runtime_auto_classes() -> None:
    """Create stable persistent subclasses whenever the module is imported.

    Ray workers may unpickle classes in a fresh interpreter. Registering every
    runtime BaseAuto subclass at module import guarantees that a class referenced
    as ``loto.auto_campaign.trial_persistence.PersistentAutoX`` exists there too.
    """

    try:
        import inspect

        import neuralforecast.auto as auto_module
        from neuralforecast.common._base_auto import BaseAuto
    except ImportError:
        return

    for exported_name in getattr(auto_module, "__all__", ()):
        value = getattr(auto_module, exported_name, None)
        if inspect.isclass(value) and value is not BaseAuto and issubclass(value, BaseAuto):
            persistent_auto_class(value)


_register_runtime_auto_classes()
