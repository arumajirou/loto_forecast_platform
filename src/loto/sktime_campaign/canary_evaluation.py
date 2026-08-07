from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REQUIRED_BASELINES = {
    "random",
    "fixed",
    "mean",
    "median",
    "last",
    "frequency",
    "seasonal_naive",
}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} must use strict UTC Z format") from exc


class RegisteredSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_target: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    shadow_candidate_id: str = Field(min_length=1)
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class P9ActivationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    p9_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p9_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p9_post_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["SHADOW_CANARY_ACTIVATED"]
    promotion_status: Literal["CANARY_ACTIVE_NOT_PRIMARY"]
    primary_binding_unchanged: Literal[True] = True
    prediction_publication_allowed: Literal[False] = False
    automatic_primary_promotion: Literal[False] = False
    subject: RegisteredSubject


class PositionRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: int
    maximum: int

    @model_validator(mode="after")
    def validate_bounds(self) -> "PositionRange":
        if self.minimum > self.maximum:
            raise ValueError("position range minimum exceeds maximum")
        return self


class LockedCandidatePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    role: Literal["shadow", "baseline"]
    seed: int | None = None
    actuals_known_at_prediction: Literal[False] = False
    prediction_scope: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    values: list[list[int]] = Field(min_length=1)


class ShadowEvaluationWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    window_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    activation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    shadow_candidate_id: str = Field(min_length=1)
    prediction_locked_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    actuals_revealed_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    prediction_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actual_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    history_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    draw_ids: list[str] = Field(min_length=1)
    position_ranges: list[PositionRange] = Field(min_length=1)
    actuals: list[list[int]] = Field(min_length=1)
    predictions: list[LockedCandidatePrediction] = Field(min_length=8)

    @model_validator(mode="after")
    def validate_window(self) -> "ShadowEvaluationWindow":
        locked = _parse_utc(
            self.prediction_locked_at_utc,
            label="prediction_locked_at_utc",
        )
        revealed = _parse_utc(
            self.actuals_revealed_at_utc,
            label="actuals_revealed_at_utc",
        )
        if revealed <= locked:
            raise ValueError("actual reveal must follow prediction lock")
        if len(self.draw_ids) != len(set(self.draw_ids)):
            raise ValueError("draw IDs must be unique within a window")
        if len(self.actuals) != len(self.draw_ids):
            raise ValueError("actual row count must match draw IDs")
        width = len(self.position_ranges)
        for row in self.actuals:
            _validate_row(row, self.position_ranges, label="actual")
        keys: list[tuple[str, int | None]] = []
        for item in self.predictions:
            keys.append((item.candidate_id, item.seed))
            if len(item.values) != len(self.draw_ids):
                raise ValueError("prediction row count must match draw IDs")
            for row in item.values:
                if len(row) != width:
                    raise ValueError("prediction position count mismatch")
                _validate_row(row, self.position_ranges, label="prediction")
        if len(keys) != len(set(keys)):
            raise ValueError("candidate and seed pairs must be unique")
        shadow_rows = [item for item in self.predictions if item.role == "shadow"]
        if len(shadow_rows) != 1:
            raise ValueError("exactly one shadow prediction is required")
        if shadow_rows[0].candidate_id != self.shadow_candidate_id:
            raise ValueError("shadow candidate ID mismatch")
        if shadow_rows[0].seed is not None:
            raise ValueError("deployed shadow prediction cannot select a seed")
        baseline_ids = {
            item.candidate_id for item in self.predictions if item.role == "baseline"
        }
        if baseline_ids != REQUIRED_BASELINES:
            raise ValueError("required baseline inventory mismatch")
        random_seeds = sorted(
            item.seed
            for item in self.predictions
            if item.candidate_id == "random" and item.seed is not None
        )
        if random_seeds != [1, 2, 3]:
            raise ValueError("random baseline must contain seeds 1, 2, and 3")
        for item in self.predictions:
            if item.candidate_id == "random":
                if item.seed not in {1, 2, 3}:
                    raise ValueError("random baseline seed inventory mismatch")
            elif item.seed is not None:
                raise ValueError("only the random baseline may carry a seed")
        expected_lock = canonical_sha256(prediction_lock_payload(self))
        if expected_lock != self.prediction_lock_sha256:
            raise ValueError("prediction lock SHA-256 mismatch")
        return self


def _validate_row(
    row: list[int],
    ranges: list[PositionRange],
    *,
    label: str,
) -> None:
    if len(row) != len(ranges):
        raise ValueError(f"{label} position count mismatch")
    for index, (value, bounds) in enumerate(zip(row, ranges, strict=True)):
        if value < bounds.minimum or value > bounds.maximum:
            raise ValueError(f"{label} value outside position range at {index}")


def prediction_lock_payload(window: ShadowEvaluationWindow) -> dict[str, Any]:
    return {
        "schema_version": window.schema_version,
        "window_id": window.window_id,
        "activation_id": window.activation_id,
        "shadow_candidate_id": window.shadow_candidate_id,
        "prediction_locked_at_utc": window.prediction_locked_at_utc,
        "history_snapshot_sha256": window.history_snapshot_sha256,
        "prediction_code_sha256": window.prediction_code_sha256,
        "draw_ids": window.draw_ids,
        "position_ranges": [item.model_dump(mode="json") for item in window.position_ranges],
        "predictions": [item.model_dump(mode="json") for item in window.predictions],
        "actuals_known_at_lock": False,
        "prediction_publication_allowed": False,
    }


class CanaryEvaluationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_windows: int = Field(default=3, ge=3)
    minimum_total_draws: int = Field(default=3, ge=3)
    minimum_weighted_hit_at_1: float = Field(default=0.90, ge=0.0, le=1.0)
    minimum_worst_window_hit_at_1: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_weighted_mae: float = Field(default=1.0, ge=0.0)
    require_all_baseline_superiority: Literal[True] = True
    strict_improvement_over_at_least_one_baseline: Literal[True] = True
    primary_promotion_executed: Literal[False] = False
    primary_binding_changed: Literal[False] = False
    prediction_publication_allowed: Literal[False] = False
    automatic_primary_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False
    automatic_rollback: Literal[False] = False


class CanaryEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["evaluate_shadow_canary"] = "evaluate_shadow_canary"
    output_dir: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    p9: P9ActivationEvidence
    policy: CanaryEvaluationPolicy = Field(default_factory=CanaryEvaluationPolicy)
    windows: list[ShadowEvaluationWindow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> "CanaryEvaluationRequest":
        evaluated = _parse_utc(self.evaluated_at_utc, label="evaluated_at_utc")
        ids = [item.window_id for item in self.windows]
        if len(ids) != len(set(ids)):
            raise ValueError("window IDs must be unique")
        locks = [item.prediction_lock_sha256 for item in self.windows]
        if len(locks) != len(set(locks)):
            raise ValueError("prediction lock seals must be unique")
        all_draw_ids: list[str] = []
        ranges = self.windows[0].position_ranges
        for window in self.windows:
            if window.activation_id != self.p9.activation_id:
                raise ValueError("window activation ID differs from P9")
            if window.shadow_candidate_id != self.p9.subject.shadow_candidate_id:
                raise ValueError("window shadow candidate differs from P9")
            if window.position_ranges != ranges:
                raise ValueError("position ranges must stay constant across windows")
            reveal = _parse_utc(
                window.actuals_revealed_at_utc,
                label="actuals_revealed_at_utc",
            )
            if reveal > evaluated:
                raise ValueError("evaluation precedes actual reveal")
            all_draw_ids.extend(window.draw_ids)
        if len(all_draw_ids) != len(set(all_draw_ids)):
            raise ValueError("draw IDs may not overlap across windows")
        return self


def _metrics(actuals: list[list[int]], predictions: list[list[int]]) -> dict[str, Any]:
    draw_count = len(actuals)
    position_count = len(actuals[0])
    absolute_sum = 0.0
    square_sum = 0.0
    hit_count = 0
    all_position_hits = 0
    position_hits = [0] * position_count
    for actual_row, prediction_row in zip(actuals, predictions, strict=True):
        row_all_hit = True
        for index, (actual, predicted) in enumerate(
            zip(actual_row, prediction_row, strict=True)
        ):
            error = float(predicted - actual)
            absolute_sum += abs(error)
            square_sum += error * error
            is_hit = abs(error) <= 1.0
            if is_hit:
                hit_count += 1
                position_hits[index] += 1
            else:
                row_all_hit = False
        if row_all_hit:
            all_position_hits += 1
    value_count = draw_count * position_count
    mse = square_sum / value_count
    return {
        "draw_count": draw_count,
        "position_count": position_count,
        "value_count": value_count,
        "hit_at_1": hit_count / value_count,
        "all_position_hit_at_1": all_position_hits / draw_count,
        "position_hit_at_1": [value / draw_count for value in position_hits],
        "mae": absolute_sum / value_count,
        "mse": mse,
        "rmse": math.sqrt(mse),
    }


def _weighted_population_variance(
    values: list[float],
    weights: list[int],
) -> float:
    total = sum(weights)
    mean = sum(value * weight for value, weight in zip(values, weights, strict=True)) / total
    return sum(
        weight * ((value - mean) ** 2)
        for value, weight in zip(values, weights, strict=True)
    ) / total


def _aggregate_metric_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    value_weights = [int(item["value_count"]) for item in rows]
    draw_weights = [int(item["draw_count"]) for item in rows]
    total_values = sum(value_weights)
    total_draws = sum(draw_weights)
    weighted_mse = sum(
        float(item["mse"]) * weight
        for item, weight in zip(rows, value_weights, strict=True)
    ) / total_values
    position_count = int(rows[0]["position_count"])
    position_hit = []
    for index in range(position_count):
        position_hit.append(
            sum(
                float(item["position_hit_at_1"][index]) * weight
                for item, weight in zip(rows, draw_weights, strict=True)
            )
            / total_draws
        )
    summary: dict[str, Any] = {
        "window_count": len(rows),
        "draw_count": total_draws,
        "value_count": total_values,
        "mean": {
            "hit_at_1": sum(
                float(item["hit_at_1"]) * weight
                for item, weight in zip(rows, value_weights, strict=True)
            )
            / total_values,
            "all_position_hit_at_1": sum(
                float(item["all_position_hit_at_1"]) * weight
                for item, weight in zip(rows, draw_weights, strict=True)
            )
            / total_draws,
            "position_hit_at_1": position_hit,
            "mae": sum(
                float(item["mae"]) * weight
                for item, weight in zip(rows, value_weights, strict=True)
            )
            / total_values,
            "mse": weighted_mse,
            "rmse": math.sqrt(weighted_mse),
        },
        "variance": {},
        "worst": {
            "hit_at_1": min(float(item["hit_at_1"]) for item in rows),
            "all_position_hit_at_1": min(
                float(item["all_position_hit_at_1"]) for item in rows
            ),
            "position_hit_at_1": [
                min(float(item["position_hit_at_1"][index]) for item in rows)
                for index in range(position_count)
            ],
            "mae": max(float(item["mae"]) for item in rows),
            "mse": max(float(item["mse"]) for item in rows),
            "rmse": max(float(item["rmse"]) for item in rows),
        },
    }
    for key in ["hit_at_1", "mae", "mse", "rmse"]:
        summary["variance"][key] = _weighted_population_variance(
            [float(item[key]) for item in rows],
            value_weights,
        )
    summary["variance"]["all_position_hit_at_1"] = _weighted_population_variance(
        [float(item["all_position_hit_at_1"]) for item in rows],
        draw_weights,
    )
    summary["variance"]["position_hit_at_1"] = [
        _weighted_population_variance(
            [float(item["position_hit_at_1"][index]) for item in rows],
            draw_weights,
        )
        for index in range(position_count)
    ]
    return summary


def evaluate_shadow_canary(request: CanaryEvaluationRequest) -> dict[str, Any]:
    window_metrics: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int | None], list[dict[str, Any]]] = defaultdict(list)
    for window in request.windows:
        for item in window.predictions:
            metrics = _metrics(window.actuals, item.values)
            record = {
                "window_id": window.window_id,
                "candidate_id": item.candidate_id,
                "role": item.role,
                "seed": item.seed,
                **metrics,
            }
            window_metrics.append(record)
            grouped[(item.candidate_id, item.seed)].append(record)

    per_series = {
        f"{candidate_id}::seed={seed}": {
            "candidate_id": candidate_id,
            "seed": seed,
            **_aggregate_metric_rows(rows),
        }
        for (candidate_id, seed), rows in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1]),
        )
    }

    candidate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for payload in per_series.values():
        candidate_groups[str(payload["candidate_id"])].append(payload)

    candidate_metrics: dict[str, Any] = {}
    for candidate_id, seed_rows in sorted(candidate_groups.items()):
        if candidate_id == "random":
            seed_count = len(seed_rows)
            mean_metrics = {}
            variance_metrics = {}
            worst_metrics = {}
            for key in ["hit_at_1", "all_position_hit_at_1", "mae", "mse", "rmse"]:
                values = [float(row["mean"][key]) for row in seed_rows]
                mean_metrics[key] = sum(values) / seed_count
                variance_metrics[key] = sum(
                    (value - mean_metrics[key]) ** 2 for value in values
                ) / seed_count
                worst_metrics[key] = min(values) if "hit" in key else max(values)
            position_count = len(seed_rows[0]["mean"]["position_hit_at_1"])
            mean_metrics["position_hit_at_1"] = [
                sum(float(row["mean"]["position_hit_at_1"][index]) for row in seed_rows)
                / seed_count
                for index in range(position_count)
            ]
            variance_metrics["position_hit_at_1"] = [
                sum(
                    (
                        float(row["mean"]["position_hit_at_1"][index])
                        - mean_metrics["position_hit_at_1"][index]
                    )
                    ** 2
                    for row in seed_rows
                )
                / seed_count
                for index in range(position_count)
            ]
            worst_metrics["position_hit_at_1"] = [
                min(float(row["mean"]["position_hit_at_1"][index]) for row in seed_rows)
                for index in range(position_count)
            ]
            candidate_metrics[candidate_id] = {
                "candidate_id": candidate_id,
                "seed_count": seed_count,
                "seed_summaries": seed_rows,
                "mean": mean_metrics,
                "variance": variance_metrics,
                "worst": worst_metrics,
                "window_count": len(request.windows),
                "draw_count": sum(len(window.draw_ids) for window in request.windows),
            }
        else:
            if len(seed_rows) != 1:
                raise ValueError("non-random candidate unexpectedly has seed variants")
            candidate_metrics[candidate_id] = seed_rows[0]

    shadow = candidate_metrics[request.p9.subject.shadow_candidate_id]
    comparisons = []
    for baseline_id in sorted(REQUIRED_BASELINES):
        baseline = candidate_metrics[baseline_id]
        hit_delta = float(shadow["mean"]["hit_at_1"]) - float(
            baseline["mean"]["hit_at_1"]
        )
        mae_delta = float(baseline["mean"]["mae"]) - float(shadow["mean"]["mae"])
        comparisons.append(
            {
                "baseline_id": baseline_id,
                "shadow_hit_at_1": shadow["mean"]["hit_at_1"],
                "baseline_hit_at_1": baseline["mean"]["hit_at_1"],
                "hit_delta_shadow_minus_baseline": hit_delta,
                "shadow_mae": shadow["mean"]["mae"],
                "baseline_mae": baseline["mean"]["mae"],
                "mae_improvement_baseline_minus_shadow": mae_delta,
                "no_worse": hit_delta >= 0.0 and mae_delta >= 0.0,
                "strictly_better": hit_delta > 0.0 or mae_delta > 0.0,
            }
        )

    rules = [
        {
            "rule": "minimum_windows",
            "passed": len(request.windows) >= request.policy.minimum_windows,
            "observed": len(request.windows),
            "required": request.policy.minimum_windows,
        },
        {
            "rule": "minimum_total_draws",
            "passed": sum(len(item.draw_ids) for item in request.windows)
            >= request.policy.minimum_total_draws,
            "observed": sum(len(item.draw_ids) for item in request.windows),
            "required": request.policy.minimum_total_draws,
        },
        {
            "rule": "weighted_hit_at_1",
            "passed": float(shadow["mean"]["hit_at_1"])
            >= request.policy.minimum_weighted_hit_at_1,
            "observed": shadow["mean"]["hit_at_1"],
            "required": request.policy.minimum_weighted_hit_at_1,
        },
        {
            "rule": "worst_window_hit_at_1",
            "passed": float(shadow["worst"]["hit_at_1"])
            >= request.policy.minimum_worst_window_hit_at_1,
            "observed": shadow["worst"]["hit_at_1"],
            "required": request.policy.minimum_worst_window_hit_at_1,
        },
        {
            "rule": "weighted_mae",
            "passed": float(shadow["mean"]["mae"])
            <= request.policy.maximum_weighted_mae,
            "observed": shadow["mean"]["mae"],
            "required_maximum": request.policy.maximum_weighted_mae,
        },
        {
            "rule": "all_baseline_superiority",
            "passed": all(item["no_worse"] for item in comparisons),
            "failed_baselines": [
                item["baseline_id"] for item in comparisons if not item["no_worse"]
            ],
        },
        {
            "rule": "strict_improvement_over_at_least_one_baseline",
            "passed": any(item["strictly_better"] for item in comparisons),
            "strictly_better_baselines": [
                item["baseline_id"]
                for item in comparisons
                if item["strictly_better"]
            ],
        },
    ]

    ordered_decisions = [
        ("minimum_windows", "BLOCKED_INSUFFICIENT_WINDOWS"),
        ("minimum_total_draws", "BLOCKED_INSUFFICIENT_DRAWS"),
        ("weighted_hit_at_1", "REJECTED_PRIMARY_HIT_TARGET"),
        ("worst_window_hit_at_1", "REJECTED_WORST_WINDOW"),
        ("weighted_mae", "REJECTED_MAE_LIMIT"),
        ("all_baseline_superiority", "REJECTED_BASELINE_SUPERIORITY"),
        (
            "strict_improvement_over_at_least_one_baseline",
            "REJECTED_NO_STRICT_BASELINE_IMPROVEMENT",
        ),
    ]
    by_name = {item["rule"]: item for item in rules}
    decision = "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW"
    for rule_name, failed_decision in ordered_decisions:
        if not by_name[rule_name]["passed"]:
            decision = failed_decision
            break

    return {
        "schema_version": "1.0",
        "status": "PASS",
        "stage": "shadow_canary_actual_scoring",
        "run_id": request.run_id,
        "decision": decision,
        "window_metrics": window_metrics,
        "per_series_metrics": per_series,
        "candidate_metrics": candidate_metrics,
        "baseline_comparison": comparisons,
        "rule_evaluation": rules,
        "shadow_candidate_id": request.p9.subject.shadow_candidate_id,
        "window_count": len(request.windows),
        "total_draws": sum(len(item.draw_ids) for item in request.windows),
        "primary_promotion_eligible": decision
        == "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW",
        "primary_promotion_executed": False,
        "primary_binding_changed": False,
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
        "automatic_retraining": False,
        "automatic_rollback": False,
        "next_action": (
            "P11_SEPARATE_PRIMARY_PROMOTION_REVIEW_REQUIRED"
            if decision == "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW"
            else "REVIEW_CANARY_CONTINUATION_OR_DEACTIVATION"
        ),
    }
