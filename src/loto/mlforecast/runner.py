from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from loto.mlforecast.artifacts import (
    _canonical_frame_hash,
    _environment,
    _write_manifest,
    atomic_write_text,
    sha256_file,
    utc_now,
)
from loto.mlforecast.contracts import MLForecastRunConfig, RunMode
from loto.mlforecast.data import chronological_split, load_config, load_frame, validate_panel
from loto.mlforecast.metrics import evaluate_prediction, make_baseline_predictions
from loto.mlforecast.runtime import (
    _fit_predict,
    _prediction_columns,
    _save_and_certify,
    _update_for_prospective,
)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    status: str
    metrics: pd.DataFrame


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
            raise ValueError(f"prospective exogenous data is missing columns: {sorted(missing)}")
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

    metrics = pd.DataFrame(rows).sort_values(["hit_at_1", "mae"], ascending=[False, True])
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
    prospective = _update_for_prospective(model, holdout, config, prospective_features)
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


def run_from_paths(
    data_path: Path,
    config_path: Path,
    prospective_exogenous_path: Path | None = None,
) -> RunResult:
    prospective = (
        load_frame(prospective_exogenous_path) if prospective_exogenous_path is not None else None
    )
    return run(load_frame(data_path), load_config(config_path), prospective)
