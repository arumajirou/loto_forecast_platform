from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Callable, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.sktime_campaign.benchmark import (
    FORMAL_BASELINES,
    FORMAL_MODELS,
    BaselineId,
    ChronologicalSplit,
    GameMatrix,
    baseline_predictions,
    canonical_sha256,
    compute_metrics,
    postprocess_predictions,
)
from loto.sktime_campaign.matrix import MODEL_SPECS, _distribution_versions, _load_class
from loto.sktime_campaign.protocol import ProviderStatus, SmokeModelId


class RollingOriginSpec(BaseModel):
    """Expanding-window OOF geometry contained entirely inside Train."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    initial_train_rows: int = Field(ge=8)
    fold_horizon: int = Field(ge=1)
    step_length: int = Field(ge=1)
    minimum_folds: int = Field(default=3, ge=2)


class RollingOriginRequest(BaseModel):
    """P3 request for Train-only OOF and pre-actual Holdout prediction locking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["rolling_origin_oof_holdout_lock"] = "rolling_origin_oof_holdout_lock"
    output_dir: str = Field(min_length=1)
    environment_lane: Literal["classic-py312"] = "classic-py312"
    expected_sktime_version: Literal["1.0.1"] = "1.0.1"
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset: GameMatrix
    split: ChronologicalSplit
    rolling_origin: RollingOriginSpec
    baseline_ids: list[BaselineId] = Field(default_factory=lambda: list(FORMAL_BASELINES))
    model_ids: list[SmokeModelId] = Field(default_factory=lambda: list(FORMAL_MODELS))
    random_seeds: list[int] = Field(default_factory=lambda: [1, 2, 3], min_length=3)
    season_length: int = Field(default=7, ge=1)
    prediction_postprocess: Literal["round_clip"] = "round_clip"
    device: Literal["cpu"] = "cpu"

    @model_validator(mode="after")
    def validate_request(self) -> "RollingOriginRequest":
        if self.split.total_rows != len(self.dataset.values):
            raise ValueError("split row total must equal dataset row count")
        if len(set(self.baseline_ids)) != len(self.baseline_ids):
            raise ValueError("baseline_ids must be unique")
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("model_ids must be unique")
        if len(set(self.random_seeds)) != len(self.random_seeds):
            raise ValueError("random_seeds must be unique")
        if self.random_seeds != sorted(self.random_seeds):
            raise ValueError("random_seeds must be sorted")
        folds = build_rolling_folds_from_counts(
            train_rows=self.split.train_rows,
            spec=self.rolling_origin,
        )
        if len(folds) < self.rolling_origin.minimum_folds:
            raise ValueError("rolling-origin geometry yields too few folds")
        return self


ModelPredictor = Callable[[SmokeModelId, np.ndarray, int, RollingOriginRequest], dict[str, Any]]


def _payload_sha256(payload: Any) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build_rolling_folds_from_counts(
    *,
    train_rows: int,
    spec: RollingOriginSpec,
) -> list[dict[str, int]]:
    """Build deterministic expanding-window folds that never leave Train."""

    folds: list[dict[str, int]] = []
    train_end = spec.initial_train_rows
    fold_id = 0
    while train_end + spec.fold_horizon <= train_rows:
        test_start = train_end
        test_end = test_start + spec.fold_horizon
        folds.append(
            {
                "fold_id": fold_id,
                "train_start": 0,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )
        fold_id += 1
        train_end += spec.step_length
    return folds


def build_rolling_folds(request: RollingOriginRequest) -> list[dict[str, Any]]:
    folds = build_rolling_folds_from_counts(
        train_rows=request.split.train_rows,
        spec=request.rolling_origin,
    )
    draw_no = request.dataset.draw_no
    return [
        {
            **fold,
            "train_draw_no": draw_no[fold["train_start"] : fold["train_end"]],
            "test_draw_no": draw_no[fold["test_start"] : fold["test_end"]],
            "fit_scope": "OOF_TRAIN_PREFIX_ONLY",
            "evaluation_scope": "OOF_TRAIN_FUTURE_BLOCK_ONLY",
        }
        for fold in folds
    ]


def _predict_sktime_matrix(
    model_id: SmokeModelId,
    train: np.ndarray,
    horizon: int,
    request: RollingOriginRequest,
) -> dict[str, Any]:
    spec = MODEL_SPECS[model_id]
    dependency_versions, missing = _distribution_versions(spec.required_distributions)
    base = {
        "candidate_id": model_id.value,
        "candidate_kind": "sktime",
        "class_path": spec.class_path,
        "constructor": spec.constructor,
        "required_distributions": list(spec.required_distributions),
        "dependency_versions": dependency_versions,
        "missing_dependencies": missing,
        "position_status": {},
    }
    if missing:
        return {**base, "status": ProviderStatus.UNAVAILABLE.value}

    import pandas as pd

    raw = np.empty((horizon, train.shape[1]), dtype=float)
    for column, position_name in enumerate(request.dataset.position_names):
        try:
            estimator_class = _load_class(spec.class_path)
            estimator = estimator_class(**spec.constructor)
            y = pd.Series(
                train[:, column],
                index=pd.RangeIndex(1, train.shape[0] + 1, name="draw_no"),
                name=position_name,
                dtype=float,
            )
            fh = list(range(1, horizon + 1))
            estimator.fit(y, fh=fh)
            prediction = estimator.predict(fh=fh)
            if isinstance(prediction, pd.DataFrame):
                if prediction.shape[1] != 1:
                    raise RuntimeError("prediction must contain one target column")
                values = prediction.iloc[:, 0].to_numpy(dtype=float)
            elif isinstance(prediction, pd.Series):
                values = prediction.to_numpy(dtype=float)
            else:
                raise RuntimeError("prediction must be a pandas Series or DataFrame")
            expected_index = [len(y) + step for step in fh]
            if [int(value) for value in prediction.index.tolist()] != expected_index:
                raise RuntimeError("prediction index mismatch")
            if values.shape != (horizon,) or not np.isfinite(values).all():
                raise RuntimeError("prediction shape or finite-value check failed")
            raw[:, column] = values
            base["position_status"][position_name] = "PASS"
        except Exception as exc:
            base["position_status"][position_name] = "FAILED"
            return {
                **base,
                "status": ProviderStatus.FAILED.value,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
    return {**base, "status": ProviderStatus.PASS.value, "raw_predictions": raw.tolist()}


def _candidate_seeds(
    candidate_kind: str,
    candidate_id: str,
    request: RollingOriginRequest,
) -> list[int]:
    if candidate_kind == "baseline" and candidate_id == BaselineId.RANDOM_UNIFORM.value:
        return request.random_seeds
    return [1]


def _predict_candidate(
    *,
    candidate_kind: str,
    candidate_id: str,
    seed: int,
    train: np.ndarray,
    horizon: int,
    request: RollingOriginRequest,
    model_predictor: ModelPredictor,
) -> dict[str, Any]:
    if candidate_kind == "baseline":
        baseline_id = BaselineId(candidate_id)
        try:
            raw = baseline_predictions(
                baseline_id,
                train=train,
                horizon=horizon,
                legal_min=request.dataset.legal_min,
                legal_max=request.dataset.legal_max,
                season_length=request.season_length,
                seed=seed,
            )
            return {
                "candidate_id": candidate_id,
                "candidate_kind": "baseline",
                "seed": seed,
                "status": ProviderStatus.PASS.value,
                "raw_predictions": raw.tolist(),
            }
        except Exception as exc:
            return {
                "candidate_id": candidate_id,
                "candidate_kind": "baseline",
                "seed": seed,
                "status": ProviderStatus.FAILED.value,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
    model_id = SmokeModelId(candidate_id)
    return {
        **model_predictor(model_id, train, horizon, request),
        "seed": seed,
    }


def _candidate_inventory(request: RollingOriginRequest) -> list[tuple[str, str]]:
    return [
        *(("baseline", item.value) for item in request.baseline_ids),
        *(("sktime", item.value) for item in request.model_ids),
    ]


def expected_candidate_seed_keys(
    request: RollingOriginRequest,
) -> list[tuple[str, str, int]]:
    """Return the exact candidate/seed inventory required per fold and lock."""

    keys: list[tuple[str, str, int]] = []
    for candidate_kind, candidate_id in _candidate_inventory(request):
        for seed in _candidate_seeds(candidate_kind, candidate_id, request):
            keys.append((candidate_kind, candidate_id, seed))
    return keys


def run_oof(
    request: RollingOriginRequest,
    *,
    model_predictor: ModelPredictor | None = None,
) -> dict[str, Any]:
    """Evaluate all candidates on identical Train-contained rolling folds."""

    predictor = _predict_sktime_matrix if model_predictor is None else model_predictor
    train_only = np.asarray(
        request.dataset.values[: request.split.train_rows],
        dtype=float,
    )
    fold_rows = build_rolling_folds(request)
    results: list[dict[str, Any]] = []
    for fold in fold_rows:
        train = train_only[fold["train_start"] : fold["train_end"]].copy()
        actual = train_only[fold["test_start"] : fold["test_end"]].copy()
        for candidate_kind, candidate_id in _candidate_inventory(request):
            for seed in _candidate_seeds(candidate_kind, candidate_id, request):
                row = _predict_candidate(
                    candidate_kind=candidate_kind,
                    candidate_id=candidate_id,
                    seed=seed,
                    train=train,
                    horizon=actual.shape[0],
                    request=request,
                    model_predictor=predictor,
                )
                row.update(
                    {
                        "fold_id": fold["fold_id"],
                        "fit_scope": "OOF_TRAIN_PREFIX_ONLY",
                        "evaluation_scope": "OOF_TRAIN_FUTURE_BLOCK_ONLY",
                        "train_values_sha256": canonical_sha256(train.tolist()),
                        "actual_values": actual.tolist(),
                        "actual_values_sha256": canonical_sha256(actual.tolist()),
                        "test_draw_no": fold["test_draw_no"],
                    }
                )
                if row.get("status") == ProviderStatus.PASS.value:
                    raw = np.asarray(row["raw_predictions"], dtype=float)
                    prediction = postprocess_predictions(
                        raw,
                        legal_min=request.dataset.legal_min,
                        legal_max=request.dataset.legal_max,
                    )
                    row["predictions"] = prediction.tolist()
                    row["metrics"] = compute_metrics(
                        actual,
                        prediction,
                        position_names=request.dataset.position_names,
                    )
                results.append(row)
    return {"folds": fold_rows, "results": results}


def aggregate_oof_results(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aggregate folds per seed, then seeds per candidate; never select one best seed."""

    metric_names = ("hit_at_1", "all_position_hit_at_1", "mae", "mse", "rmse")
    per_seed_groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["candidate_kind"]), str(row["candidate_id"]), int(row["seed"]))
        per_seed_groups.setdefault(key, []).append(row)

    seed_metrics: list[dict[str, Any]] = []
    for (kind, candidate_id, seed), group in sorted(per_seed_groups.items()):
        passed = [row for row in group if row.get("status") == "PASS"]
        group_statuses = [str(row.get("status")) for row in group]
        if len(passed) == len(group):
            seed_status = "PASS"
        elif passed:
            seed_status = "PARTIAL"
        elif all(status == "UNAVAILABLE" for status in group_statuses):
            seed_status = "UNAVAILABLE"
        else:
            seed_status = "FAILED"
        item: dict[str, Any] = {
            "candidate_kind": kind,
            "candidate_id": candidate_id,
            "seed": seed,
            "fold_count": len(group),
            "passed_fold_count": len(passed),
            "status": seed_status,
        }
        if passed:
            item["metrics"] = {}
            for name in metric_names:
                values = np.asarray([row["metrics"][name] for row in passed], dtype=float)
                item["metrics"][name] = {
                    "mean": float(values.mean()),
                    "variance": float(values.var()),
                    "worst": float(values.min() if "hit" in name else values.max()),
                }
        seed_metrics.append(item)

    candidate_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in seed_metrics:
        candidate_groups.setdefault(
            (str(row["candidate_kind"]), str(row["candidate_id"])), []
        ).append(row)
    aggregates: list[dict[str, Any]] = []
    for (kind, candidate_id), group in sorted(candidate_groups.items()):
        passed = [row for row in group if row.get("status") == "PASS"]
        group_statuses = [str(row.get("status")) for row in group]
        if len(passed) == len(group):
            candidate_status = "PASS"
        elif passed:
            candidate_status = "PARTIAL"
        elif all(status == "UNAVAILABLE" for status in group_statuses):
            candidate_status = "UNAVAILABLE"
        else:
            candidate_status = "FAILED"
        item = {
            "candidate_kind": kind,
            "candidate_id": candidate_id,
            "seed_count": len(group),
            "passed_seed_count": len(passed),
            "seeds": [row["seed"] for row in group],
            "status": candidate_status,
        }
        if passed:
            item["metrics"] = {}
            for name in metric_names:
                values = np.asarray([row["metrics"][name]["mean"] for row in passed], dtype=float)
                item["metrics"][name] = {
                    "mean": float(values.mean()),
                    "variance": float(values.var()),
                    "worst": float(values.min() if "hit" in name else values.max()),
                }
        aggregates.append(item)
    return seed_metrics, aggregates


def build_oof_leaderboard(aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [row for row in aggregates if row.get("status") == "PASS" and "metrics" in row]
    return sorted(
        eligible,
        key=lambda row: (
            -row["metrics"]["hit_at_1"]["mean"],
            -row["metrics"]["all_position_hit_at_1"]["mean"],
            row["metrics"]["mae"]["mean"],
            row["candidate_id"],
        ),
    )


def lock_holdout_predictions(
    request: RollingOriginRequest,
    *,
    selected_candidate_id: str | None,
    sealed_at_utc: str | None = None,
    model_predictor: ModelPredictor | None = None,
) -> dict[str, Any]:
    """Freeze every candidate/seed prediction without reading Holdout actual values."""

    predictor = _predict_sktime_matrix if model_predictor is None else model_predictor
    visible_rows = request.split.train_rows + request.split.validation_rows
    visible = np.asarray(
        request.dataset.values[:visible_rows],
        dtype=float,
    )
    horizon = request.split.holdout_rows
    rows: list[dict[str, Any]] = []
    for candidate_kind, candidate_id in _candidate_inventory(request):
        for seed in _candidate_seeds(candidate_kind, candidate_id, request):
            row = _predict_candidate(
                candidate_kind=candidate_kind,
                candidate_id=candidate_id,
                seed=seed,
                train=visible,
                horizon=horizon,
                request=request,
                model_predictor=predictor,
            )
            row.update(
                {
                    "fit_scope": "TRAIN_PLUS_VALIDATION_ONLY",
                    "forecast_scope": "HOLDOUT_PREDICTION_ONLY",
                    "actuals_known": False,
                    "evaluation_status": "NOT_SCORED",
                }
            )
            if row.get("status") == "PASS":
                raw = np.asarray(row["raw_predictions"], dtype=float)
                prediction = postprocess_predictions(
                    raw,
                    legal_min=request.dataset.legal_min,
                    legal_max=request.dataset.legal_max,
                )
                row["predictions"] = prediction.tolist()
                row["prediction_sha256"] = canonical_sha256(row["predictions"])
            rows.append(row)

    timestamp = sealed_at_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "schema_version": "1.0",
        "lock_scope": "ALL_CANDIDATES_ALL_SEEDS_BEFORE_HOLDOUT_ACTUALS",
        "run_id": request.run_id,
        "sealed_at_utc": timestamp,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "validation_artifact_sha256": request.validation_artifact_sha256,
        "visible_rows": visible_rows,
        "visible_values_sha256": canonical_sha256(visible.tolist()),
        "holdout_draw_no": request.dataset.draw_no[visible_rows:],
        "holdout_draw_no_sha256": canonical_sha256(request.dataset.draw_no[visible_rows:]),
        "selected_oof_candidate_id": selected_candidate_id,
        "all_candidate_predictions_locked": True,
        "actuals_known": False,
        "evaluation_status": "NOT_SCORED",
        "prediction_rows": rows,
    }
    return {**payload, "seal_sha256": _payload_sha256(payload)}


def verify_prediction_lock(lock: dict[str, Any]) -> None:
    seal = str(lock.get("seal_sha256", ""))
    payload = {key: value for key, value in lock.items() if key != "seal_sha256"}
    if len(seal) != 64 or _payload_sha256(payload) != seal:
        raise ValueError("prediction-lock SHA-256 mismatch")
    if lock.get("lock_scope") != "ALL_CANDIDATES_ALL_SEEDS_BEFORE_HOLDOUT_ACTUALS":
        raise ValueError("prediction lock scope mismatch")
    if lock.get("all_candidate_predictions_locked") is not True:
        raise ValueError("prediction lock does not cover all candidates")
    if lock.get("actuals_known") is not False or lock.get("evaluation_status") != "NOT_SCORED":
        raise ValueError("prediction lock incorrectly claims known/scored Holdout actuals")
    timestamp = str(lock.get("sealed_at_utc", ""))
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("prediction lock UTC timestamp is invalid") from exc
    for row in lock.get("prediction_rows", []):
        if "metrics" in row or "actual_values" in row:
            raise ValueError("Holdout lock contains score or actual values")
        if row.get("fit_scope") != "TRAIN_PLUS_VALIDATION_ONLY":
            raise ValueError("prediction row fit scope mismatch")
        if row.get("forecast_scope") != "HOLDOUT_PREDICTION_ONLY":
            raise ValueError("prediction row forecast scope mismatch")
        if row.get("actuals_known") is not False:
            raise ValueError("prediction row incorrectly claims known actuals")
        if row.get("evaluation_status") != "NOT_SCORED":
            raise ValueError("prediction row was scored before actuals")
        if row.get("status") == "PASS":
            prediction = np.asarray(row.get("predictions"), dtype=float)
            if prediction.ndim != 2 or not np.isfinite(prediction).all():
                raise ValueError("locked prediction shape or finite check failed")
            if row.get("prediction_sha256") != canonical_sha256(row.get("predictions")):
                raise ValueError("locked prediction row SHA-256 mismatch")


def run_p3(
    request: RollingOriginRequest,
    *,
    sealed_at_utc: str | None = None,
    model_predictor: ModelPredictor | None = None,
) -> dict[str, Any]:
    oof = run_oof(request, model_predictor=model_predictor)
    seed_metrics, aggregates = aggregate_oof_results(oof["results"])
    leaderboard = build_oof_leaderboard(aggregates)
    selected = leaderboard[0]["candidate_id"] if leaderboard else None
    lock = lock_holdout_predictions(
        request,
        selected_candidate_id=selected,
        sealed_at_utc=sealed_at_utc,
        model_predictor=model_predictor,
    )
    verify_prediction_lock(lock)
    all_oof_pass = bool(oof["results"]) and all(
        row.get("status") == "PASS" for row in oof["results"]
    )
    all_lock_pass = bool(lock["prediction_rows"]) and all(
        row.get("status") == "PASS" for row in lock["prediction_rows"]
    )
    combined_rows = oof["results"] + lock["prediction_rows"]
    any_pass = any(row.get("status") == "PASS" for row in combined_rows)
    all_unavailable = bool(combined_rows) and all(
        row.get("status") == "UNAVAILABLE" for row in combined_rows
    )
    if all_oof_pass and all_lock_pass:
        status = "PASS"
    elif any_pass:
        status = "PARTIAL"
    elif all_unavailable:
        status = "UNAVAILABLE"
    else:
        status = "FAILED"
    return {
        "schema_version": "1.0",
        "status": status,
        "stage": "oof_and_holdout_prediction_lock",
        "folds": oof["folds"],
        "oof_results": oof["results"],
        "oof_seed_metrics": seed_metrics,
        "oof_candidate_aggregates": aggregates,
        "oof_leaderboard": leaderboard,
        "selected_oof_candidate_id": selected,
        "holdout_prediction_lock": lock,
        "holdout_status": "PREDICTIONS_LOCKED_NOT_SCORED",
        "promotion_status": "NOT_PROMOTED",
    }
