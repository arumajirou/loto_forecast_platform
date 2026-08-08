from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.sktime_campaign.benchmark import (
    FORMAL_BASELINES,
    FORMAL_MODELS,
    BaselineId,
    baseline_predictions,
    canonical_sha256,
    compute_metrics,
    postprocess_predictions,
)
from loto.sktime_campaign.matrix import MODEL_SPECS, _distribution_versions, _load_class
from loto.sktime_campaign.protocol import ProviderStatus, SmokeModelId


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"{label} must use strict UTC Z format") from exc


class ObservedHistory(BaseModel):
    """Only values already observed before the Prospective seal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    draw_no: list[int] = Field(min_length=8)
    position_names: list[str] = Field(min_length=1)
    values: list[list[float]] = Field(min_length=8)
    legal_min: list[int] = Field(min_length=1)
    legal_max: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_history(self) -> ObservedHistory:
        width = len(self.position_names)
        if len(set(self.position_names)) != width:
            raise ValueError("position_names must be unique")
        if len(self.draw_no) != len(self.values):
            raise ValueError("draw_no and values row counts differ")
        if self.draw_no != sorted(self.draw_no):
            raise ValueError("history draw_no must be sorted")
        if len(set(self.draw_no)) != len(self.draw_no):
            raise ValueError("history draw_no must be unique")
        if any(
            right != left + 1 for left, right in zip(self.draw_no, self.draw_no[1:], strict=False)
        ):
            raise ValueError("history draw_no must be gap-free")
        if len(self.legal_min) != width or len(self.legal_max) != width:
            raise ValueError("legal bounds must match position count")
        for row in self.values:
            if len(row) != width:
                raise ValueError("history row width mismatch")
            if not np.isfinite(np.asarray(row, dtype=float)).all():
                raise ValueError("history values must be finite")
        return self


class ProspectiveRequest(BaseModel):
    """P5A request for all-candidate shadow predictions before future actuals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["prospective_shadow_lock"] = "prospective_shadow_lock"
    output_dir: str = Field(min_length=1)
    environment_lane: Literal["classic-py312"] = "classic-py312"
    expected_sktime_version: Literal["1.0.1"] = "1.0.1"
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p4_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p4_selected_oof_candidate_id: str = Field(min_length=1)
    p4_promotion_status: Literal["NOT_PROMOTED"] = "NOT_PROMOTED"
    history: ObservedHistory
    prospective_draw_no: list[int] = Field(min_length=1)
    baseline_ids: list[BaselineId] = Field(default_factory=lambda: list(FORMAL_BASELINES))
    model_ids: list[SmokeModelId] = Field(default_factory=lambda: list(FORMAL_MODELS))
    random_seeds: list[int] = Field(default_factory=lambda: [1, 2, 3], min_length=3)
    season_length: int = Field(default=7, ge=1)
    max_workers: int = Field(default=8, ge=1, le=8)
    prediction_postprocess: Literal["round_clip"] = "round_clip"
    device: Literal["cpu"] = "cpu"
    actuals_known: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> ProspectiveRequest:
        if self.prospective_draw_no != sorted(self.prospective_draw_no):
            raise ValueError("prospective_draw_no must be sorted")
        if len(set(self.prospective_draw_no)) != len(self.prospective_draw_no):
            raise ValueError("prospective_draw_no must be unique")
        if self.prospective_draw_no[0] != self.history.draw_no[-1] + 1:
            raise ValueError("prospective draw IDs must start after history cutoff")
        if any(
            right != left + 1
            for left, right in zip(
                self.prospective_draw_no, self.prospective_draw_no[1:], strict=False
            )
        ):
            raise ValueError("prospective draw IDs must be gap-free")
        if len(set(self.baseline_ids)) != len(self.baseline_ids):
            raise ValueError("baseline_ids must be unique")
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("model_ids must be unique")
        if self.random_seeds != sorted(self.random_seeds):
            raise ValueError("random_seeds must be sorted")
        if len(set(self.random_seeds)) != len(self.random_seeds):
            raise ValueError("random_seeds must be unique")
        candidate_ids = {item.value for item in self.baseline_ids} | {
            item.value for item in self.model_ids
        }
        if self.p4_selected_oof_candidate_id not in candidate_ids:
            raise ValueError("P4-selected OOF candidate is not in P5 inventory")
        return self


ModelPredictor = Callable[
    [SmokeModelId, np.ndarray, int, ProspectiveRequest],
    dict[str, Any],
]


def expected_candidate_seed_keys(
    request: ProspectiveRequest,
) -> list[tuple[str, str, int]]:
    keys: list[tuple[str, str, int]] = []
    for baseline in request.baseline_ids:
        seeds = request.random_seeds if baseline is BaselineId.RANDOM_UNIFORM else [1]
        keys.extend(("baseline", baseline.value, seed) for seed in seeds)
    keys.extend(("sktime", model.value, 1) for model in request.model_ids)
    return keys


def _predict_sktime_matrix(
    model_id: SmokeModelId,
    history: np.ndarray,
    horizon: int,
    request: ProspectiveRequest,
) -> dict[str, Any]:
    spec = MODEL_SPECS[model_id]
    dependency_versions, missing = _distribution_versions(spec.required_distributions)
    base = {
        "candidate_kind": "sktime",
        "candidate_id": model_id.value,
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

    raw = np.empty((horizon, history.shape[1]), dtype=float)
    for column, position_name in enumerate(request.history.position_names):
        try:
            estimator_class = _load_class(spec.class_path)
            estimator = estimator_class(**spec.constructor)
            y = pd.Series(
                history[:, column],
                index=pd.RangeIndex(1, history.shape[0] + 1, name="draw_no"),
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
                raise RuntimeError("prediction must be pandas Series or DataFrame")
            expected_index = [len(y) + step for step in fh]
            if [int(value) for value in prediction.index.tolist()] != expected_index:
                raise RuntimeError("prediction index mismatch")
            if values.shape != (horizon,) or not np.isfinite(values).all():
                raise RuntimeError("prediction shape or finite check failed")
            raw[:, column] = values
            base["position_status"][position_name] = "PASS"
        except Exception as exc:
            base["position_status"][position_name] = "FAILED"
            return {
                **base,
                "status": ProviderStatus.FAILED.value,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
    return {
        **base,
        "status": ProviderStatus.PASS.value,
        "raw_predictions": raw.tolist(),
    }


def _predict_one(
    key: tuple[str, str, int],
    request: ProspectiveRequest,
    history: np.ndarray,
    predictor: ModelPredictor,
) -> dict[str, Any]:
    kind, candidate_id, seed = key
    horizon = len(request.prospective_draw_no)
    if kind == "baseline":
        try:
            raw = baseline_predictions(
                BaselineId(candidate_id),
                train=history,
                horizon=horizon,
                legal_min=request.history.legal_min,
                legal_max=request.history.legal_max,
                season_length=request.season_length,
                seed=seed,
            )
            row: dict[str, Any] = {
                "candidate_kind": kind,
                "candidate_id": candidate_id,
                "seed": seed,
                "status": ProviderStatus.PASS.value,
                "raw_predictions": raw.tolist(),
            }
        except Exception as exc:
            row = {
                "candidate_kind": kind,
                "candidate_id": candidate_id,
                "seed": seed,
                "status": ProviderStatus.FAILED.value,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
    else:
        row = {
            **predictor(SmokeModelId(candidate_id), history, horizon, request),
            "seed": seed,
        }

    row.update(
        {
            "fit_scope": "OBSERVED_HISTORY_ONLY",
            "forecast_scope": "PROSPECTIVE_DRAW_IDS_ONLY",
            "actuals_known": False,
            "evaluation_status": "NOT_SCORED",
            "device": "cpu",
            "cpu_fallback": False,
            "pid": os.getpid(),
            "worker_backend": "thread_pool",
        }
    )
    if row.get("status") == ProviderStatus.PASS.value:
        raw = np.asarray(row["raw_predictions"], dtype=float)
        prediction = postprocess_predictions(
            raw,
            legal_min=request.history.legal_min,
            legal_max=request.history.legal_max,
        )
        row["predictions"] = prediction.tolist()
        row["prediction_shape"] = list(prediction.shape)
        row["prediction_finite"] = True
        row["prediction_sha256"] = canonical_sha256(row["predictions"])
    return row


def verify_prospective_lock(lock: dict[str, Any]) -> None:
    seal = str(lock.get("seal_sha256", ""))
    payload = {key: value for key, value in lock.items() if key != "seal_sha256"}
    if len(seal) != 64 or _payload_sha256(payload) != seal:
        raise ValueError("Prospective prediction-lock SHA-256 mismatch")
    if lock.get("actuals_known") is not False:
        raise ValueError("Prospective lock incorrectly claims known actuals")
    if lock.get("evaluation_status") != "NOT_SCORED":
        raise ValueError("Prospective lock was scored before actuals")
    if lock.get("promotion_status") != "SHADOW_NOT_PROMOTED":
        raise ValueError("Prospective lock incorrectly claims promotion")
    _parse_utc(str(lock.get("sealed_at_utc", "")), label="sealed_at_utc")
    for row in lock.get("prediction_rows", []):
        if row.get("fit_scope") != "OBSERVED_HISTORY_ONLY":
            raise ValueError("Prospective row fit scope mismatch")
        if row.get("forecast_scope") != "PROSPECTIVE_DRAW_IDS_ONLY":
            raise ValueError("Prospective row forecast scope mismatch")
        if row.get("actuals_known") is not False:
            raise ValueError("Prospective row incorrectly claims known actuals")
        if row.get("evaluation_status") != "NOT_SCORED":
            raise ValueError("Prospective row was scored before actuals")
        if row.get("status") == "PASS":
            prediction = np.asarray(row.get("predictions"), dtype=float)
            if prediction.ndim != 2 or not np.isfinite(prediction).all():
                raise ValueError("Prospective prediction shape or finite check failed")
            if row.get("prediction_sha256") != canonical_sha256(row.get("predictions")):
                raise ValueError("Prospective prediction row SHA-256 mismatch")


def run_prospective_lock(
    request: ProspectiveRequest,
    *,
    sealed_at_utc: str | None = None,
    model_predictor: ModelPredictor | None = None,
) -> dict[str, Any]:
    predictor = _predict_sktime_matrix if model_predictor is None else model_predictor
    history = np.asarray(request.history.values, dtype=float)
    keys = expected_candidate_seed_keys(request)
    rows_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
        futures = {
            executor.submit(_predict_one, key, request, history, predictor): key for key in keys
        }
        for future in as_completed(futures):
            key = futures[future]
            rows_by_key[key] = future.result()
    rows = [rows_by_key[key] for key in keys]

    timestamp = sealed_at_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "schema_version": "1.0",
        "lock_scope": "ALL_CANDIDATES_ALL_SEEDS_BEFORE_PROSPECTIVE_ACTUALS",
        "run_id": request.run_id,
        "sealed_at_utc": timestamp,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "p4_artifact_sha256": request.p4_artifact_sha256,
        "shadow_candidate_id": request.p4_selected_oof_candidate_id,
        "selection_source": "P3_OOF_VIA_VERIFIED_P4_LINEAGE",
        "history_rows": len(request.history.values),
        "history_cutoff_draw_no": request.history.draw_no[-1],
        "history_sha256": canonical_sha256(
            {
                "draw_no": request.history.draw_no,
                "values": request.history.values,
            }
        ),
        "position_names": request.history.position_names,
        "legal_min": request.history.legal_min,
        "legal_max": request.history.legal_max,
        "prospective_draw_no": request.prospective_draw_no,
        "prospective_draw_no_sha256": canonical_sha256(request.prospective_draw_no),
        "max_workers": request.max_workers,
        "thread_limits": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "actuals_known": False,
        "evaluation_status": "NOT_SCORED",
        "promotion_status": "SHADOW_NOT_PROMOTED",
        "prediction_rows": rows,
    }
    lock = {**payload, "seal_sha256": _payload_sha256(payload)}
    verify_prospective_lock(lock)

    all_pass = bool(rows) and all(row.get("status") == "PASS" for row in rows)
    any_pass = any(row.get("status") == "PASS" for row in rows)
    all_unavailable = bool(rows) and all(row.get("status") == "UNAVAILABLE" for row in rows)
    status = (
        "PASS"
        if all_pass
        else ("PARTIAL" if any_pass else ("UNAVAILABLE" if all_unavailable else "FAILED"))
    )
    return {
        "schema_version": "1.0",
        "status": status,
        "stage": "prospective_shadow_prediction_lock",
        "prediction_lock": lock,
        "shadow_candidate_id": request.p4_selected_oof_candidate_id,
        "prospective_status": "PREDICTIONS_LOCKED_NOT_SCORED",
        "promotion_status": "SHADOW_NOT_PROMOTED",
    }


class ProspectiveActuals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    revealed_at_utc: str
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    draw_no: list[int] = Field(min_length=1)
    position_names: list[str] = Field(min_length=1)
    values: list[list[float]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_actuals(self) -> ProspectiveActuals:
        if len(self.draw_no) != len(self.values):
            raise ValueError("actual draw and value row counts differ")
        if len(set(self.position_names)) != len(self.position_names):
            raise ValueError("actual position_names must be unique")
        width = len(self.position_names)
        for row in self.values:
            if len(row) != width:
                raise ValueError("actual row width mismatch")
            if not np.isfinite(np.asarray(row, dtype=float)).all():
                raise ValueError("actual values must be finite")
        _parse_utc(self.revealed_at_utc, label="revealed_at_utc")
        return self


class DriftPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_at_1_target: float = Field(default=0.90, ge=0.0, le=1.0)
    warning_hit_drop: float = Field(default=0.05, ge=0.0, le=1.0)
    critical_hit_drop: float = Field(default=0.10, ge=0.0, le=1.0)
    warning_mae_increase: float = Field(default=0.50, ge=0.0)
    critical_mae_increase: float = Field(default=1.00, ge=0.0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> DriftPolicy:
        if self.critical_hit_drop < self.warning_hit_drop:
            raise ValueError("critical_hit_drop must be >= warning_hit_drop")
        if self.critical_mae_increase < self.warning_mae_increase:
            raise ValueError("critical_mae_increase must be >= warning_mae_increase")
        return self


class ProspectiveMonitoringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["prospective_monitor"] = "prospective_monitor"
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    prediction_lock: dict[str, Any]
    actuals: ProspectiveActuals
    holdout_reference_metrics: dict[str, Any]
    policy: DriftPolicy = Field(default_factory=DriftPolicy)

    @model_validator(mode="after")
    def validate_monitoring(self) -> ProspectiveMonitoringRequest:
        verify_prospective_lock(self.prediction_lock)
        sealed = _parse_utc(
            str(self.prediction_lock["sealed_at_utc"]),
            label="sealed_at_utc",
        )
        revealed = _parse_utc(
            self.actuals.revealed_at_utc,
            label="revealed_at_utc",
        )
        if revealed <= sealed:
            raise ValueError("Prospective actual reveal must follow prediction seal")
        if self.actuals.draw_no != self.prediction_lock.get("prospective_draw_no"):
            raise ValueError("Prospective actual draw identities differ from lock")
        if self.actuals.position_names != self.prediction_lock.get("position_names"):
            raise ValueError("Prospective actual positions differ from lock")
        return self


def _aggregate_scored_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (str(row["candidate_kind"]), str(row["candidate_id"])),
            [],
        ).append(row)
    metrics = ("hit_at_1", "all_position_hit_at_1", "mae", "mse", "rmse")
    output: list[dict[str, Any]] = []
    for (kind, candidate_id), group in sorted(groups.items()):
        passed = [row for row in group if row.get("status") == "PASS"]
        item: dict[str, Any] = {
            "candidate_kind": kind,
            "candidate_id": candidate_id,
            "status": (
                "PASS"
                if len(passed) == len(group)
                else ("PARTIAL" if passed else group[0].get("status", "FAILED"))
            ),
            "seed_count": len(group),
            "passed_seed_count": len(passed),
            "seeds": [row["seed"] for row in group],
        }
        if passed:
            item["metrics"] = {}
            for metric in metrics:
                values = np.asarray(
                    [row["metrics"][metric] for row in passed],
                    dtype=float,
                )
                item["metrics"][metric] = {
                    "mean": float(values.mean()),
                    "variance": float(values.var()),
                    "worst": float(values.min() if "hit" in metric else values.max()),
                }
        output.append(item)
    return output


def _leaderboard(aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [row for row in aggregates if row.get("status") == "PASS" and "metrics" in row],
        key=lambda row: (
            -row["metrics"]["hit_at_1"]["mean"],
            -row["metrics"]["all_position_hit_at_1"]["mean"],
            row["metrics"]["mae"]["mean"],
            row["candidate_id"],
        ),
    )


def monitor_prospective(
    request: ProspectiveMonitoringRequest,
) -> dict[str, Any]:
    actual = np.asarray(request.actuals.values, dtype=float)
    rows: list[dict[str, Any]] = []
    for locked in request.prediction_lock["prediction_rows"]:
        row = {
            "candidate_kind": locked["candidate_kind"],
            "candidate_id": locked["candidate_id"],
            "seed": locked["seed"],
            "status": locked["status"],
            "locked_prediction_sha256": locked.get("prediction_sha256"),
            "prediction_source": "P5_LOCK_ONLY_NO_REFIT_NO_REPREDICT",
        }
        if locked.get("status") == "PASS":
            prediction = np.asarray(locked.get("predictions"), dtype=float)
            if prediction.shape != actual.shape:
                raise ValueError("Prospective prediction and actual shape mismatch")
            row["predictions"] = locked["predictions"]
            row["metrics"] = compute_metrics(
                actual,
                prediction,
                position_names=request.actuals.position_names,
            )
        rows.append(row)

    aggregates = _aggregate_scored_rows(rows)
    leaderboard = _leaderboard(aggregates)
    shadow_id = str(request.prediction_lock["shadow_candidate_id"])
    shadow = next(
        (row for row in aggregates if row["candidate_id"] == shadow_id),
        None,
    )
    reference = request.holdout_reference_metrics
    alerts: list[dict[str, Any]] = []
    level = "STABLE"
    if not shadow or shadow.get("status") != "PASS":
        level = "CRITICAL"
        alerts.append(
            {
                "code": "SHADOW_SCORE_UNAVAILABLE",
                "severity": "CRITICAL",
            }
        )
    else:
        current_hit = shadow["metrics"]["hit_at_1"]["mean"]
        current_mae = shadow["metrics"]["mae"]["mean"]
        reference_hit = float(reference["hit_at_1"]["mean"])
        reference_mae = float(reference["mae"]["mean"])
        hit_drop = reference_hit - current_hit
        mae_increase = current_mae - reference_mae
        if (
            current_hit < request.policy.hit_at_1_target
            or hit_drop >= request.policy.critical_hit_drop
            or mae_increase >= request.policy.critical_mae_increase
        ):
            level = "CRITICAL"
        elif (
            hit_drop >= request.policy.warning_hit_drop
            or mae_increase >= request.policy.warning_mae_increase
        ):
            level = "WARNING"
        if current_hit < request.policy.hit_at_1_target:
            alerts.append(
                {
                    "code": "HIT_AT_1_BELOW_TARGET",
                    "severity": "CRITICAL",
                    "value": current_hit,
                    "target": request.policy.hit_at_1_target,
                }
            )
        if hit_drop >= request.policy.warning_hit_drop:
            alerts.append(
                {
                    "code": "HIT_AT_1_DROP",
                    "severity": (
                        "CRITICAL" if hit_drop >= request.policy.critical_hit_drop else "WARNING"
                    ),
                    "value": hit_drop,
                }
            )
        if mae_increase >= request.policy.warning_mae_increase:
            alerts.append(
                {
                    "code": "MAE_INCREASE",
                    "severity": (
                        "CRITICAL"
                        if mae_increase >= request.policy.critical_mae_increase
                        else "WARNING"
                    ),
                    "value": mae_increase,
                }
            )

    recommendation = {
        "STABLE": "CONTINUE_SHADOW",
        "WARNING": "CONTINUE_SHADOW_REVIEW_REQUIRED",
        "CRITICAL": "BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED",
    }[level]
    all_pass = bool(rows) and all(row.get("status") == "PASS" for row in rows)
    status = "PASS" if all_pass else "PARTIAL"
    return {
        "schema_version": "1.0",
        "status": status,
        "stage": "prospective_monitoring",
        "shadow_candidate_id": shadow_id,
        "score_rows": rows,
        "candidate_aggregates": aggregates,
        "leaderboard": leaderboard,
        "drift_status": level,
        "alerts": alerts,
        "recommendation": recommendation,
        "automatic_retraining": False,
        "automatic_promotion": False,
        "promotion_status": "NOT_PROMOTED",
    }
