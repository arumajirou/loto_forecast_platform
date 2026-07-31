from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from loto.coverage.core import (
    CoverageConfig,
    PredictionSet,
    augment_with_residual_offsets,
    evaluate_candidates,
    generate_candidate_pool,
    greedy_coverage_select,
    position_probabilities,
    simultaneous_conformal_radius,
)
from loto.data.canonical import canonicalize_loto7
from loto.data.lineage import atomic_write_json


def _numbers(frame: pd.DataFrame) -> np.ndarray:
    return frame[[f"n{i}" for i in range(1, 8)]].to_numpy(dtype=int)


def _point_forecast(history: np.ndarray, method: str) -> np.ndarray:
    if method == "median":
        values = np.median(history, axis=0)
    elif method == "historic-average":
        values = np.mean(history, axis=0)
    elif method == "recent-median":
        values = np.median(history[-min(100, len(history)) :], axis=0)
    else:
        raise ValueError(f"unknown point method: {method}")
    rounded = np.rint(values).astype(int)
    rounded = np.clip(rounded, 1, 37)
    for i in range(1, 7):
        rounded[i] = max(rounded[i], rounded[i - 1] + 1)
    if rounded[-1] > 37:
        rounded = np.arange(31, 38)
    return rounded


def _walk_forward(
    data: np.ndarray, start: int, end: int, methods: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    actual: list[np.ndarray] = []
    predicted: list[np.ndarray] = []
    for index in range(start, end):
        history = data[:index]
        points = np.vstack([_point_forecast(history, method) for method in methods])
        prediction = np.rint(np.median(points, axis=0)).astype(int)
        for i in range(1, 7):
            prediction[i] = max(prediction[i], prediction[i - 1] + 1)
        actual.append(data[index])
        predicted.append(prediction)
    return np.asarray(actual), np.asarray(predicted)


def _load_config(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("coverage config must be a mapping")
    return raw


def run_coverage_experiment(config_path: str | Path) -> dict[str, Any]:
    raw = _load_config(config_path)
    data_cfg = raw.get("data", {})
    output = Path(raw.get("output", "runs/coverage-90"))
    output.mkdir(parents=True, exist_ok=True)
    frame, manifest = canonicalize_loto7(pd.read_csv(data_cfg["input"]), source=data_cfg["input"])
    data = _numbers(frame)
    split = raw.get("split", {})
    test_size = int(split.get("test_size", 50))
    calibration_size = int(split.get("calibration_size", 100))
    validation_size = int(split.get("validation_size", 100))
    min_train = int(split.get("min_train_size", 300))
    required = min_train + calibration_size + validation_size + test_size
    if len(data) < required:
        raise ValueError(f"not enough draws: need {required}, found {len(data)}")
    test_start = len(data) - test_size
    validation_start = test_start - validation_size
    calibration_start = validation_start - calibration_size
    if calibration_start < min_train:
        raise ValueError("split leaves fewer than min_train_size draws")

    methods = list(raw.get("models", ["median", "historic-average", "recent-median"]))
    cal_actual, cal_pred = _walk_forward(data, calibration_start, validation_start, methods)
    val_actual, val_pred = _walk_forward(data, validation_start, test_start, methods)
    cfg = CoverageConfig(**raw.get("coverage", {}))
    conformal_radius = simultaneous_conformal_radius(
        cal_actual, cal_pred, cfg.target_coverage + cfg.calibration_margin
    )

    center = _point_forecast(data[:test_start], "median")
    method_centers = np.vstack([_point_forecast(data[:test_start], method) for method in methods])
    ensemble_center = np.rint(np.median(method_centers, axis=0)).astype(int)
    residuals = cal_actual - cal_pred
    probs = position_probabilities(data[:test_start], ensemble_center)
    pool = generate_candidate_pool(
        probs,
        per_position_top=cfg.per_position_top,
        beam_width=cfg.beam_width,
        pool_size=cfg.pool_size,
    )
    pool.extend(
        augment_with_residual_offsets(
            ensemble_center, residuals, radius=max(1, min(conformal_radius, 3)), limit=cfg.pool_size
        )
    )
    pool.extend([tuple(center.tolist()), tuple(ensemble_center.tolist())])
    pool = list(dict.fromkeys(pool))[: cfg.pool_size]

    selected, trace = greedy_coverage_select(
        cal_actual,
        pool,
        target_coverage=min(1.0, cfg.target_coverage + cfg.calibration_margin),
        tolerance=cfg.tolerance,
        max_candidates=cfg.max_candidates,
        diversity_penalty=cfg.diversity_penalty,
    )
    calibration_eval = evaluate_candidates(cal_actual, selected, cfg.tolerance)
    validation_eval = evaluate_candidates(val_actual, selected, cfg.tolerance)
    prediction_set = PredictionSet(
        candidates=selected,
        target_coverage=cfg.target_coverage,
        calibration_coverage=calibration_eval.row_within_tolerance,
        tolerance=cfg.tolerance,
        conformal_radius=conformal_radius,
        metadata={
            "methods": methods,
            "pool_size": len(pool),
            "ensemble_center": ensemble_center.tolist(),
            "calibration_margin": cfg.calibration_margin,
        },
    )
    candidates_frame = pd.DataFrame(selected, columns=[f"n{i}" for i in range(1, 8)])
    candidates_frame.insert(0, "rank", np.arange(1, len(candidates_frame) + 1))
    candidates_frame.to_csv(output / "prediction_set.csv", index=False)
    atomic_write_json(output / "prediction_set.json", prediction_set.to_dict())
    atomic_write_json(output / "selection_trace.json", trace)
    summary = {
        "schema_version": "1.0.0",
        "status": "TARGET_MET"
        if validation_eval.row_within_tolerance >= cfg.target_coverage
        else "TARGET_NOT_MET",
        "data_version": manifest.data_version,
        "draws": len(data),
        "split": {
            "train_end": calibration_start,
            "calibration": [calibration_start, validation_start],
            "validation": [validation_start, test_start],
            "protected_test": [test_start, len(data)],
        },
        "target_coverage": cfg.target_coverage,
        "tolerance": cfg.tolerance,
        "candidate_count": len(selected),
        "pool_size": len(pool),
        "conformal_radius": conformal_radius,
        "calibration": calibration_eval.to_dict(),
        "validation": validation_eval.to_dict(),
        "protected_test_evaluated": False,
        "artifacts": {
            "prediction_set_csv": str(output / "prediction_set.csv"),
            "prediction_set_json": str(output / "prediction_set.json"),
            "selection_trace": str(output / "selection_trace.json"),
        },
        "note": "90% is a measured coverage target, not a guaranteed lottery win probability. Protected test remains unopened.",
    }
    atomic_write_json(output / "coverage_summary.json", summary)
    return summary


def certify_coverage_experiment(
    config_path: str | Path, prediction_set_path: str | Path | None = None
) -> dict[str, Any]:
    raw = _load_config(config_path)
    output = Path(raw.get("output", "runs/coverage-90"))
    summary_path = output / "coverage_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("coverage_summary.json not found; run coverage build first")
    prior = json.loads(summary_path.read_text(encoding="utf-8"))
    set_path = Path(prediction_set_path) if prediction_set_path else output / "prediction_set.json"
    prediction_set = json.loads(set_path.read_text(encoding="utf-8"))
    candidates = prediction_set["candidates"]
    frame, manifest = canonicalize_loto7(
        pd.read_csv(raw["data"]["input"]), source=raw["data"]["input"]
    )
    data = _numbers(frame)
    start, end = prior["split"]["protected_test"]
    actual = data[int(start) : int(end)]
    cfg = CoverageConfig(**raw.get("coverage", {}))
    evaluation = evaluate_candidates(actual, candidates, cfg.tolerance)
    result = {
        "schema_version": "1.0.0",
        "status": "CERTIFIED_TARGET_MET"
        if evaluation.row_within_tolerance >= cfg.target_coverage
        else "CERTIFIED_TARGET_NOT_MET",
        "data_version": manifest.data_version,
        "target_coverage": cfg.target_coverage,
        "protected_test": evaluation.to_dict(),
        "prediction_set_sha256": __import__("hashlib").sha256(set_path.read_bytes()).hexdigest(),
        "warning": "Certification opens the protected test. Do not tune on this result; create a new future holdout for subsequent changes.",
    }
    atomic_write_json(output / "coverage_certification.json", result)
    prior["protected_test_evaluated"] = True
    prior["certification"] = result
    atomic_write_json(summary_path, prior)
    return result
