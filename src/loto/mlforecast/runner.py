from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from loto.mlforecast.contracts import MLForecastRunConfig, RunMode
from loto.mlforecast.factory import (
    auto_fit_kwargs,
    build_auto_forecast,
    build_core_forecast,
    build_prediction_intervals,
    core_fit_kwargs,
    hit_at_1_objective,
)
from loto.mlforecast.metrics import evaluate_prediction, make_baseline_predictions


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    status: str
    metrics: pd.DataFrame


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _canonical_frame_hash(
    frame: pd.DataFrame,
    *,
    id_col: str,
    time_col: str,
) -> str:
    ordered = frame.sort_values([id_col, time_col]).reset_index(drop=True)
    return sha256_bytes(ordered.to_csv(index=False, lineterminator="\n").encode())


def validate_panel(frame: pd.DataFrame, config: MLForecastRunConfig) -> pd.DataFrame:
    required = {config.id_col, config.time_col, config.target_col}
    if missing := required - set(frame.columns):
        raise ValueError(f"input data is missing required columns: {sorted(missing)}")
    result = frame.copy()
    if result[list(required)].isna().any().any():
        raise ValueError("id, time and target columns cannot contain missing values")
    if result.duplicated([config.id_col, config.time_col]).any():
        raise ValueError("duplicate id/time rows are not allowed")
    result[config.target_col] = pd.to_numeric(result[config.target_col], errors="raise")
    if not np.isfinite(result[config.target_col].to_numpy(float)).all():
        raise ValueError("target values must be finite")
    result = result.sort_values([config.id_col, config.time_col]).reset_index(drop=True)
    for series_id, group in result.groupby(config.id_col, sort=False):
        if len(group) <= config.holdout_size:
            raise ValueError(
                f"series {series_id!r} requires more than {config.holdout_size} rows"
            )
        timestamps = group[config.time_col]
        if not timestamps.is_monotonic_increasing or timestamps.duplicated().any():
            raise ValueError(f"series {series_id!r} has invalid time ordering")
    return result


def chronological_split(
    frame: pd.DataFrame,
    config: MLForecastRunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    holdout_parts: list[pd.DataFrame] = []
    for _, group in frame.groupby(config.id_col, sort=False):
        group = group.sort_values(config.time_col)
        train_parts.append(group.iloc[: -config.holdout_size])
        holdout_parts.append(group.iloc[-config.holdout_size :])
    train = pd.concat(train_parts, ignore_index=True)
    holdout = pd.concat(holdout_parts, ignore_index=True)
    for series_id in train[config.id_col].unique():
        train_max = train.loc[train[config.id_col] == series_id, config.time_col].max()
        holdout_min = holdout.loc[holdout[config.id_col] == series_id, config.time_col].min()
        if train_max >= holdout_min:
            raise ValueError(f"chronological split failed for series {series_id!r}")
    return train, holdout


def _prediction_columns(
    prediction: pd.DataFrame,
    *,
    id_col: str,
    time_col: str,
) -> list[str]:
    excluded = {id_col, time_col, "cutoff"}
    columns = [column for column in prediction.columns if column not in excluded]
    return [column for column in columns if "-lo-" not in column and "-hi-" not in column]


def _fit_predict(
    train: pd.DataFrame,
    holdout_features: pd.DataFrame | None,
    config: MLForecastRunConfig,
) -> tuple[Any, pd.DataFrame, dict[str, Any], dict[str, pd.DataFrame]]:
    if config.mode is RunMode.CORE:
        model = build_core_forecast(config.core, seed=config.seed)
        cv_prediction = model.cross_validation(
            train,
            n_windows=config.core.cv_n_windows,
            h=config.h,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
            step_size=config.core.cv_step_size,
            static_features=config.core.static_features,
            dropna=config.core.dropna,
            keep_last_n=config.core.keep_last_n,
            refit=config.core.cv_refit,
            input_size=config.core.cv_input_size,
            prediction_intervals=build_prediction_intervals(config.core.prediction_intervals),
            level=(
                config.core.prediction_intervals.levels
                if config.core.prediction_intervals
                else None
            ),
            fitted=config.core.fitted,
            as_numpy=config.core.as_numpy,
            weight_col=config.core.weight_col,
            validate_data=config.core.validate_data,
        )
        model.fit(
            train,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
            **core_fit_kwargs(config.core),
        )
        levels = (
            config.core.prediction_intervals.levels
            if config.core.prediction_intervals
            else None
        )
        prediction = model.predict(h=config.h, level=levels, X_df=holdout_features)
        return (
            model,
            prediction,
            {"mode": "core", "models": config.core.models},
            {"core_cv_predictions": cv_prediction},
        )

    model = build_auto_forecast(config.auto)
    kwargs = auto_fit_kwargs(config.auto, seed=config.seed)
    kwargs["h"] = config.h
    model.fit(
        train,
        loss=lambda valid, fitted_train: hit_at_1_objective(
            valid,
            fitted_train,
            target_col=config.target_col,
        ),
        id_col=config.id_col,
        time_col=config.time_col,
        target_col=config.target_col,
        **{key: value for key, value in kwargs.items() if value is not None},
    )
    levels = config.auto.prediction_intervals.levels if config.auto.prediction_intervals else None
    prediction = model.predict(h=config.h, level=levels, X_df=holdout_features)
    trials = {
        f"optuna_trials_{name}": study.trials_dataframe()
        for name, study in model.results_.items()
    }
    return model, prediction, {"mode": "auto", "models": config.auto.models}, trials


def _save_and_certify(
    model: Any,
    prediction: pd.DataFrame,
    model_dir: Path,
    config: MLForecastRunConfig,
    holdout_features: pd.DataFrame | None,
) -> dict[str, Any]:
    if not config.save_model:
        return {"status": "SKIPPED", "reason": "save_model=false"}
    model_dir.mkdir(parents=True, exist_ok=True)
    if config.mode is RunMode.CORE:
        model.save(str(model_dir))
        model_paths = {"core": model_dir}
    else:
        model.save(model_dir)
        model_paths = {name: model_dir / name for name in config.auto.models}
    if not config.verify_save_load:
        return {"status": "SAVED", "paths": {key: str(value) for key, value in model_paths.items()}}

    from mlforecast import MLForecast

    checks: dict[str, Any] = {}
    for bundle_name, path in model_paths.items():
        loaded = MLForecast.load(str(path))
        levels = None
        if config.mode is RunMode.CORE and config.core.prediction_intervals:
            levels = config.core.prediction_intervals.levels
        if config.mode is RunMode.AUTO and config.auto.prediction_intervals:
            levels = config.auto.prediction_intervals.levels
        after = loaded.predict(h=config.h, level=levels, X_df=holdout_features)
        before_columns = _prediction_columns(
            prediction, id_col=config.id_col, time_col=config.time_col
        )
        after_columns = _prediction_columns(
            after, id_col=config.id_col, time_col=config.time_col
        )
        if config.mode is RunMode.AUTO:
            before_columns = [column for column in before_columns if column == bundle_name]
            after_columns = [column for column in after_columns if column == bundle_name]
        if set(before_columns) != set(after_columns) or not before_columns:
            raise ValueError(f"prediction columns changed after loading {bundle_name}")
        bundle_checks: dict[str, Any] = {}
        for column in sorted(before_columns):
            before_values = prediction.sort_values([config.id_col, config.time_col])[
                column
            ].to_numpy(float)
            after_values = after.sort_values([config.id_col, config.time_col])[
                column
            ].to_numpy(float)
            match = bool(
                before_values.shape == after_values.shape
                and np.isfinite(after_values).all()
                and np.allclose(before_values, after_values, rtol=1e-8, atol=1e-8)
            )
            bundle_checks[column] = {
                "shape": list(after_values.shape),
                "finite": bool(np.isfinite(after_values).all()),
                "prediction_match": match,
            }
            if not match:
                raise ValueError(f"save/load prediction mismatch for {column}")
        checks[bundle_name] = {"path": str(path), "predictions": bundle_checks}
    return {"status": "RUNTIME_CERTIFIED", "models": checks}


def _update_for_prospective(
    model: Any,
    holdout: pd.DataFrame,
    config: MLForecastRunConfig,
    prospective_features: pd.DataFrame | None,
) -> pd.DataFrame:
    if config.mode is RunMode.CORE:
        model.update(holdout)
        levels = (
            config.core.prediction_intervals.levels
            if config.core.prediction_intervals
            else None
        )
        return model.predict(h=config.prospective_h, level=levels, X_df=prospective_features)
    outputs: list[pd.DataFrame] = []
    levels = config.auto.prediction_intervals.levels if config.auto.prediction_intervals else None
    for name, fitted_model in model.models_.items():
        fitted_model.update(holdout)
        prediction = fitted_model.predict(
            h=config.prospective_h, level=levels, X_df=prospective_features
        )
        model_columns = [column for column in prediction.columns if column.startswith(name)]
        keep = [config.id_col, config.time_col, *model_columns]
        outputs.append(prediction[keep])
    result = outputs[0]
    for output in outputs[1:]:
        result = result.merge(output, on=[config.id_col, config.time_col], validate="one_to_one")
    return result


def _environment() -> dict[str, Any]:
    git_commit = os.getenv("GITHUB_SHA")
    if git_commit is None:
        try:
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            git_commit = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "git_commit": git_commit,
    }


def _write_manifest(run_dir: Path) -> None:
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    records = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name in excluded:
            continue
        records.append(
            {
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    atomic_write_text(
        run_dir / "ARTIFACT_MANIFEST.json",
        json.dumps({"artifacts": records}, indent=2, sort_keys=True) + "\n",
    )
    sums = "".join(f"{record['sha256']}  {record['path']}\n" for record in records)
    atomic_write_text(run_dir / "SHA256SUMS", sums)


def run(
    frame: pd.DataFrame,
    config: MLForecastRunConfig,
    prospective_features: pd.DataFrame | None = None,
) -> RunResult:
    validated = validate_panel(frame, config)
    train, holdout = chronological_split(validated, config)
    run_id = datetime.now(UTC).strftime("mlf-%Y%m%d-%H%M%S-%f")
    run_dir = config.artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    config_path = run_dir / "config.json"
    atomic_write_text(config_path, config.model_dump_json(indent=2) + "\n")
    validated.to_csv(run_dir / "input_panel.csv", index=False)
    train.to_csv(run_dir / "train.csv", index=False)
    holdout.to_csv(run_dir / "holdout.csv", index=False)

    feature_columns = [
        column
        for column in validated.columns
        if column not in {config.id_col, config.time_col, config.target_col}
    ]
    holdout_features = (
        holdout[[config.id_col, config.time_col, *feature_columns]].copy()
        if feature_columns
        else None
    )
    if prospective_features is not None:
        required_future = {config.id_col, config.time_col, *feature_columns}
        if missing := required_future - set(prospective_features.columns):
            raise ValueError(
                f"prospective exogenous data is missing columns: {sorted(missing)}"
            )
        prospective_features = prospective_features[
            [config.id_col, config.time_col, *feature_columns]
        ].copy()
    elif feature_columns:
        raise ValueError(
            "prospective exogenous data is required because dynamic/static features are present"
        )

    model, prediction, model_metadata, diagnostic_frames = _fit_predict(
        train, holdout_features, config
    )
    prediction.to_csv(run_dir / "holdout_predictions.csv", index=False)
    for name, diagnostic in diagnostic_frames.items():
        diagnostic.to_csv(run_dir / f"{name}.csv", index=False)

    rows: list[dict[str, Any]] = []
    position_frames: list[pd.DataFrame] = []
    for name in _prediction_columns(prediction, id_col=config.id_col, time_col=config.time_col):
        overall, positions = evaluate_prediction(
            holdout,
            prediction,
            prediction_col=name,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
        )
        rows.append({"model": name, "kind": "candidate", **overall})
        positions.insert(0, "model", name)
        position_frames.append(positions)

    season_length = config.auto.season_length if config.mode is RunMode.AUTO else 1
    baselines = make_baseline_predictions(
        train,
        holdout,
        id_col=config.id_col,
        time_col=config.time_col,
        target_col=config.target_col,
        seed=config.seed,
        fixed_value=config.fixed_baseline_value,
        season_length=season_length,
    )
    for name, baseline in baselines.items():
        baseline.to_csv(run_dir / f"{name}.csv", index=False)
        overall, positions = evaluate_prediction(
            holdout,
            baseline,
            prediction_col=name,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
        )
        rows.append({"model": name, "kind": "baseline", **overall})
        positions.insert(0, "model", name)
        position_frames.append(positions)

    metrics = pd.DataFrame(rows).sort_values(
        ["hit_at_1", "mae"], ascending=[False, True]
    )
    metrics.to_csv(run_dir / "metrics.csv", index=False)
    pd.concat(position_frames, ignore_index=True).to_csv(
        run_dir / "position_metrics.csv", index=False
    )

    certification = _save_and_certify(
        model,
        prediction,
        run_dir / "model",
        config,
        holdout_features,
    )
    prospective = _update_for_prospective(
        model, holdout, config, prospective_features
    )
    prospective_path = run_dir / "prospective_predictions.csv"
    prospective.to_csv(prospective_path, index=False)
    seal = {
        "sealed_at": utc_now(),
        "actual_known": False,
        "path": prospective_path.name,
        "sha256": sha256_file(prospective_path),
    }
    atomic_write_text(
        run_dir / "prospective_seal.json",
        json.dumps(seal, indent=2, sort_keys=True) + "\n",
    )

    report = {
        "status": "VERIFIED" if certification["status"] == "RUNTIME_CERTIFIED" else "EXECUTED",
        "run_id": run_id,
        "started_from_data_sha256": _canonical_frame_hash(
            validated,
            id_col=config.id_col,
            time_col=config.time_col,
        ),
        "train_rows": len(train),
        "holdout_rows": len(holdout),
        "series": int(validated[config.id_col].nunique()),
        "model": model_metadata,
        "certification": certification,
        "prospective_seal": seal,
        "environment": _environment(),
    }
    atomic_write_text(
        run_dir / "run_report.json",
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )
    _write_manifest(run_dir)
    return RunResult(run_id=run_id, run_dir=run_dir, status=report["status"], metrics=metrics)


def load_config(path: Path) -> MLForecastRunConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("configuration root must be a mapping")
    return MLForecastRunConfig.model_validate(payload)


def load_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported data format: {path.suffix}")


def run_from_paths(
    data_path: Path,
    config_path: Path,
    prospective_exogenous_path: Path | None = None,
) -> RunResult:
    prospective = (
        load_frame(prospective_exogenous_path)
        if prospective_exogenous_path is not None
        else None
    )
    return run(load_frame(data_path), load_config(config_path), prospective)
