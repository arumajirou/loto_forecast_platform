from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.sktime_campaign.benchmark import (
    FORMAL_BASELINES,
    FORMAL_MODELS,
    BaselineId,
    canonical_sha256,
    compute_metrics,
)
from loto.sktime_campaign.protocol import ProviderStatus
from loto.sktime_campaign.rolling_origin import verify_prediction_lock


class HoldoutActuals(BaseModel):
    """Independently revealed Holdout actual values and source identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    game_id: str = Field(min_length=1)
    revealed_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    draw_no: list[int] = Field(min_length=1)
    position_names: list[str] = Field(min_length=1)
    values: list[list[float]] = Field(min_length=1)
    legal_min: list[int] = Field(min_length=1)
    legal_max: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_geometry(self) -> "HoldoutActuals":
        width = len(self.position_names)
        if len(set(self.position_names)) != width:
            raise ValueError("position_names must be unique")
        if len(self.draw_no) != len(self.values):
            raise ValueError("draw_no and values row counts differ")
        if self.draw_no != sorted(self.draw_no):
            raise ValueError("draw_no must be sorted")
        if len(set(self.draw_no)) != len(self.draw_no):
            raise ValueError("draw_no must be unique")
        if len(self.legal_min) != width or len(self.legal_max) != width:
            raise ValueError("legal bounds must match position count")
        for low, high in zip(self.legal_min, self.legal_max, strict=True):
            if high < low:
                raise ValueError("legal_max must be >= legal_min")
        for row in self.values:
            if len(row) != width:
                raise ValueError("actual row width mismatch")
            for column, value in enumerate(row):
                if not math.isfinite(value):
                    raise ValueError("actual values must be finite")
                if value < self.legal_min[column]:
                    raise ValueError("actual value below legal range")
                if value > self.legal_max[column]:
                    raise ValueError("actual value above legal range")
        _parse_utc(self.revealed_at_utc, label="revealed_at_utc")
        return self


class HoldoutScoringRequest(BaseModel):
    """P4 request that scores only the immutable P3 prediction lock."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["score_sealed_holdout"] = "score_sealed_holdout"
    output_dir: str = Field(min_length=1)
    environment_lane: Literal["classic-py312"] = "classic-py312"
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_lock_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_lock_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p3_sha256sums_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scored_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    actuals: HoldoutActuals

    @model_validator(mode="after")
    def validate_times(self) -> "HoldoutScoringRequest":
        scored = _parse_utc(self.scored_at_utc, label="scored_at_utc")
        revealed = _parse_utc(
            self.actuals.revealed_at_utc,
            label="revealed_at_utc",
        )
        if scored < revealed:
            raise ValueError("scored_at_utc must not precede actual reveal")
        return self


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} is not strict UTC Z format") from exc


def expected_formal_lock_keys() -> list[tuple[str, str, int]]:
    keys: list[tuple[str, str, int]] = []
    for baseline in FORMAL_BASELINES:
        seeds = [1, 2, 3] if baseline is BaselineId.RANDOM_UNIFORM else [1]
        keys.extend(("baseline", baseline.value, seed) for seed in seeds)
    keys.extend(("sktime", model.value, 1) for model in FORMAL_MODELS)
    return keys


def lock_row_keys(lock: dict[str, Any]) -> list[tuple[str, str, int]]:
    keys = [
        (
            str(row.get("candidate_kind")),
            str(row.get("candidate_id")),
            int(row.get("seed")),
        )
        for row in lock.get("prediction_rows", [])
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("prediction lock contains duplicate candidate/seed rows")
    return keys


def validate_lock_for_scoring(
    lock: dict[str, Any],
    request: HoldoutScoringRequest,
    *,
    formal: bool,
) -> None:
    verify_prediction_lock(lock)
    if lock.get("seal_sha256") != request.expected_lock_seal_sha256:
        raise ValueError("prediction lock seal differs from expected seal")
    if lock.get("actuals_known") is not False:
        raise ValueError("prediction lock was not created before actuals")
    if lock.get("evaluation_status") != "NOT_SCORED":
        raise ValueError("prediction lock was already scored")
    if lock.get("holdout_draw_no") != request.actuals.draw_no:
        raise ValueError("Holdout draw identities do not match prediction lock")
    sealed = _parse_utc(str(lock.get("sealed_at_utc")), label="sealed_at_utc")
    revealed = _parse_utc(
        request.actuals.revealed_at_utc,
        label="revealed_at_utc",
    )
    if revealed <= sealed:
        raise ValueError("actual reveal must occur after prediction sealing")
    selected = lock.get("selected_oof_candidate_id")
    candidate_ids = {
        str(row.get("candidate_id"))
        for row in lock.get("prediction_rows", [])
    }
    if selected is None or str(selected) not in candidate_ids:
        raise ValueError("selected OOF candidate is absent from prediction lock")
    keys = lock_row_keys(lock)
    if formal and keys != expected_formal_lock_keys():
        raise ValueError("formal prediction-lock candidate/seed inventory mismatch")


def _status_from_rows(rows: list[dict[str, Any]]) -> str:
    statuses = [str(row.get("status")) for row in rows]
    if rows and all(status == ProviderStatus.PASS.value for status in statuses):
        return ProviderStatus.PASS.value
    if any(status == ProviderStatus.PASS.value for status in statuses):
        return ProviderStatus.PARTIAL.value
    if rows and all(status == ProviderStatus.UNAVAILABLE.value for status in statuses):
        return ProviderStatus.UNAVAILABLE.value
    return ProviderStatus.FAILED.value


def score_locked_rows(
    lock: dict[str, Any],
    actuals: HoldoutActuals,
) -> list[dict[str, Any]]:
    actual = np.asarray(actuals.values, dtype=float)
    rows: list[dict[str, Any]] = []
    for index, locked in enumerate(lock.get("prediction_rows", [])):
        row: dict[str, Any] = {
            "source_lock_row_index": index,
            "candidate_kind": locked.get("candidate_kind"),
            "candidate_id": locked.get("candidate_id"),
            "seed": locked.get("seed"),
            "status": locked.get("status"),
            "locked_prediction_sha256": locked.get("prediction_sha256"),
            "scoring_scope": "SEALED_PREDICTIONS_ONLY",
            "model_execution": False,
        }
        if locked.get("status") == ProviderStatus.PASS.value:
            prediction = np.asarray(locked.get("predictions"), dtype=float)
            if prediction.shape != actual.shape:
                raise ValueError("locked prediction and Holdout actual shape mismatch")
            if not np.isfinite(prediction).all():
                raise ValueError("locked prediction contains NaN or Inf")
            if canonical_sha256(locked.get("predictions")) != locked.get(
                "prediction_sha256"
            ):
                raise ValueError("locked prediction row SHA-256 mismatch")
            row["predictions"] = locked["predictions"]
            row["metrics"] = compute_metrics(
                actual,
                prediction,
                position_names=actuals.position_names,
            )
        rows.append(row)
    return rows


def aggregate_holdout_rows(
    rows: list[dict[str, Any]],
    *,
    position_names: list[str],
) -> list[dict[str, Any]]:
    scalar_metrics = (
        "hit_at_1",
        "all_position_hit_at_1",
        "mae",
        "mse",
        "rmse",
    )
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["candidate_kind"]), str(row["candidate_id"]))
        groups.setdefault(key, []).append(row)

    aggregates: list[dict[str, Any]] = []
    for (kind, candidate_id), group in sorted(groups.items()):
        passed = [row for row in group if row.get("status") == "PASS"]
        item: dict[str, Any] = {
            "candidate_kind": kind,
            "candidate_id": candidate_id,
            "status": _status_from_rows(group),
            "seed_count": len(group),
            "passed_seed_count": len(passed),
            "seeds": [int(row["seed"]) for row in group],
        }
        if passed:
            item["metrics"] = {}
            for metric in scalar_metrics:
                values = np.asarray(
                    [row["metrics"][metric] for row in passed],
                    dtype=float,
                )
                worst = values.min() if "hit" in metric else values.max()
                item["metrics"][metric] = {
                    "mean": float(values.mean()),
                    "variance": float(values.var()),
                    "worst": float(worst),
                }
            item["position_hit_at_1"] = {}
            for position in position_names:
                values = np.asarray(
                    [
                        row["metrics"]["position_hit_at_1"][position]
                        for row in passed
                    ],
                    dtype=float,
                )
                item["position_hit_at_1"][position] = {
                    "mean": float(values.mean()),
                    "variance": float(values.var()),
                    "worst": float(values.min()),
                }
        aggregates.append(item)
    return aggregates


def build_holdout_leaderboard(
    aggregates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    eligible = [
        row
        for row in aggregates
        if row.get("status") == "PASS" and "metrics" in row
    ]
    return sorted(
        eligible,
        key=lambda row: (
            -row["metrics"]["hit_at_1"]["mean"],
            -row["metrics"]["all_position_hit_at_1"]["mean"],
            row["metrics"]["mae"]["mean"],
            row["candidate_id"],
        ),
    )


def build_baseline_comparison(
    aggregates: list[dict[str, Any]],
    *,
    selected_candidate_id: str,
    leaderboard: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {str(row["candidate_id"]): row for row in aggregates}
    selected = by_id.get(selected_candidate_id)
    if selected is None or selected.get("status") != "PASS":
        return {
            "status": "UNAVAILABLE",
            "selected_oof_candidate_id": selected_candidate_id,
            "reason": "selected OOF candidate has no complete Holdout score",
        }
    selected_metrics = selected["metrics"]
    baseline_rows: list[dict[str, Any]] = []
    for row in aggregates:
        if row.get("candidate_kind") != "baseline":
            continue
        if row.get("status") != "PASS":
            baseline_rows.append(
                {
                    "candidate_id": row["candidate_id"],
                    "status": row["status"],
                }
            )
            continue
        metrics = row["metrics"]
        baseline_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "status": "PASS",
                "delta_selected_minus_baseline": {
                    "hit_at_1": (
                        selected_metrics["hit_at_1"]["mean"]
                        - metrics["hit_at_1"]["mean"]
                    ),
                    "all_position_hit_at_1": (
                        selected_metrics["all_position_hit_at_1"]["mean"]
                        - metrics["all_position_hit_at_1"]["mean"]
                    ),
                    "mae_improvement": (
                        metrics["mae"]["mean"]
                        - selected_metrics["mae"]["mean"]
                    ),
                    "mse_improvement": (
                        metrics["mse"]["mean"]
                        - selected_metrics["mse"]["mean"]
                    ),
                    "rmse_improvement": (
                        metrics["rmse"]["mean"]
                        - selected_metrics["rmse"]["mean"]
                    ),
                },
            }
        )
    rank = next(
        (
            index + 1
            for index, row in enumerate(leaderboard)
            if row["candidate_id"] == selected_candidate_id
        ),
        None,
    )
    return {
        "status": "PASS",
        "selected_oof_candidate_id": selected_candidate_id,
        "selected_holdout_rank": rank,
        "selected_metrics": selected_metrics,
        "baselines": baseline_rows,
    }


def score_holdout(
    request: HoldoutScoringRequest,
    lock: dict[str, Any],
    *,
    formal: bool = True,
) -> dict[str, Any]:
    validate_lock_for_scoring(lock, request, formal=formal)
    rows = score_locked_rows(lock, request.actuals)
    aggregates = aggregate_holdout_rows(
        rows,
        position_names=request.actuals.position_names,
    )
    leaderboard = build_holdout_leaderboard(aggregates)
    selected = str(lock["selected_oof_candidate_id"])
    comparison = build_baseline_comparison(
        aggregates,
        selected_candidate_id=selected,
        leaderboard=leaderboard,
    )
    return {
        "schema_version": "1.0",
        "status": _status_from_rows(rows),
        "stage": "holdout_score_from_sealed_predictions",
        "run_id": request.run_id,
        "scored_at_utc": request.scored_at_utc,
        "scoring_scope": "SEALED_PREDICTIONS_ONLY",
        "model_execution": False,
        "retraining": False,
        "reprediction": False,
        "prediction_lock_lineage": {
            "lock_run_id": lock["run_id"],
            "lock_sealed_at_utc": lock["sealed_at_utc"],
            "lock_seal_sha256": lock["seal_sha256"],
            "prediction_lock_file_sha256": (
                request.prediction_lock_file_sha256
            ),
            "p3_sha256sums_sha256": request.p3_sha256sums_sha256,
        },
        "actuals_identity": {
            "game_id": request.actuals.game_id,
            "revealed_at_utc": request.actuals.revealed_at_utc,
            "source_id": request.actuals.source_id,
            "source_sha256": request.actuals.source_sha256,
            "actuals_sha256": canonical_sha256(
                request.actuals.model_dump(mode="json")
            ),
            "draw_no": request.actuals.draw_no,
        },
        "holdout_results": rows,
        "candidate_aggregates": aggregates,
        "leaderboard": leaderboard,
        "baseline_comparison": comparison,
        "selected_oof_candidate_id": selected,
        "promotion_status": (
            "HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED"
        ),
    }
