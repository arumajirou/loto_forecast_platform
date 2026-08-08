from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class HistoricalForecastPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    start: int = Field(ge=1)
    forecast_horizon: int = Field(default=1, ge=1, le=512)
    stride: int = Field(default=1, ge=1, le=1000000)
    retrain: bool | int = True
    train_length: int | None = Field(default=None, ge=2)
    overlap_end: Literal[False] = False
    last_points_only: bool = True
    enable_optimization: bool = True
    compare_optimization: bool = True
    require_prefit_when_no_retrain: bool = True
    metric_atol: float = Field(default=1e-12, ge=0.0)
    metric_rtol: float = Field(default=1e-9, ge=0.0)
    residual_atol: float = Field(default=1e-12, ge=0.0)
    residual_rtol: float = Field(default=1e-9, ge=0.0)
    historical_extra_args: dict[str, Any] = Field(default_factory=dict)
    backtest_extra_args: dict[str, Any] = Field(default_factory=dict)
    residual_extra_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_policy(self) -> HistoricalForecastPolicy:
        if isinstance(self.retrain, int) and not isinstance(self.retrain, bool):
            if self.retrain < 1:
                raise ValueError("integer retrain cadence must be at least one")
        protected_historical = {
            "series",
            "start",
            "forecast_horizon",
            "stride",
            "retrain",
            "train_length",
            "overlap_end",
            "last_points_only",
            "enable_optimization",
        }
        protected_backtest = {"series", "historical_forecasts", "metric"}
        protected_residual = {"series", "historical_forecasts"}
        overlaps = {
            "historical": sorted(protected_historical & set(self.historical_extra_args)),
            "backtest": sorted(protected_backtest & set(self.backtest_extra_args)),
            "residuals": sorted(protected_residual & set(self.residual_extra_args)),
        }
        invalid = {name: values for name, values in overlaps.items() if values}
        if invalid:
            raise ValueError(f"extra arguments cannot override protected fields: {invalid}")
        return self


class HistoricalPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: int = Field(ge=0)
    target_index: int = Field(ge=0)
    position: str = Field(min_length=1)
    actual: float
    predicted: float

    @model_validator(mode="after")
    def validate_values(self) -> HistoricalPoint:
        values = np.asarray([self.actual, self.predicted], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("historical point contains NaN or Inf")
        if self.target_index < self.origin:
            raise ValueError("target_index must not precede forecast origin")
        return self


class ApiArgumentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str
    argument: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None


class ApiCallEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str
    requested_arguments: tuple[str, ...]
    effective_arguments: tuple[str, ...]
    decisions: tuple[ApiArgumentDecision, ...]


class HistoricalRuntimeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[HistoricalPoint, ...]
    backtest_metrics: dict[str, float]
    residuals: tuple[float, ...]
    observed_fit_origins: tuple[int, ...] = ()
    prefit: bool = False
    optimized_records: tuple[HistoricalPoint, ...] | None = None
    api_calls: tuple[ApiCallEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_finite(self) -> HistoricalRuntimeEvidence:
        metric_values = np.asarray(list(self.backtest_metrics.values()), dtype=float)
        if metric_values.size and not np.isfinite(metric_values).all():
            raise ValueError("backtest metrics contain NaN or Inf")
        residual_values = np.asarray(self.residuals, dtype=float)
        if residual_values.size and not np.isfinite(residual_values).all():
            raise ValueError("residuals contain NaN or Inf")
        return self


class ContractCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool
    failure_class: str | None = None
    message: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class HistoricalContractReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["HISTORICAL_EVIDENCE_CERTIFIED", "FAILED"]
    expected_origins: tuple[int, ...]
    expected_fit_origins: tuple[int, ...]
    metrics: dict[str, Any]
    residual_summary: dict[str, float]
    checks: tuple[ContractCheck, ...]
    records_sha256: str
    policy_sha256: str


RecordNormalizer = Callable[
    [Any, pd.DataFrame, tuple[str, ...], HistoricalForecastPolicy],
    tuple[HistoricalPoint, ...],
]
ResidualNormalizer = Callable[[Any], tuple[float, ...]]
BacktestNormalizer = Callable[[Any], dict[str, float]]


def expected_origins(n_rows: int, policy: HistoricalForecastPolicy) -> tuple[int, ...]:
    final_origin = n_rows - policy.forecast_horizon
    if policy.start > final_origin:
        raise ValueError("historical forecast start leaves no complete forecast window")
    return tuple(range(policy.start, final_origin + 1, policy.stride))


def expected_fit_origins(
    origins: Sequence[int],
    retrain: bool | int,
) -> tuple[int, ...]:
    ordered = tuple(int(item) for item in origins)
    if retrain is True:
        return ordered
    if retrain is False:
        return ()
    cadence = int(retrain)
    if cadence < 1:
        raise ValueError("integer retrain cadence must be at least one")
    return tuple(origin for index, origin in enumerate(ordered) if index % cadence == 0)


def _expected_keys(
    origins: Sequence[int],
    positions: Sequence[str],
    policy: HistoricalForecastPolicy,
) -> tuple[tuple[int, int, str], ...]:
    keys: list[tuple[int, int, str]] = []
    for origin in origins:
        if policy.last_points_only:
            targets = (origin + policy.forecast_horizon - 1,)
        else:
            targets = tuple(range(origin, origin + policy.forecast_horizon))
        for target in targets:
            for position in positions:
                keys.append((origin, target, position))
    return tuple(keys)


def _record_map(
    records: Sequence[HistoricalPoint],
) -> dict[tuple[int, int, str], HistoricalPoint]:
    output: dict[tuple[int, int, str], HistoricalPoint] = {}
    for record in records:
        key = (record.origin, record.target_index, record.position)
        if key in output:
            raise ValueError(f"duplicate historical point: {key}")
        output[key] = record
    return output


def validate_record_coverage(
    records: Sequence[HistoricalPoint],
    origins: Sequence[int],
    positions: Sequence[str],
    policy: HistoricalForecastPolicy,
) -> ContractCheck:
    try:
        actual = _record_map(records)
    except ValueError as error:
        return ContractCheck(
            name="historical_record_coverage",
            passed=False,
            failure_class="DUPLICATE_HISTORICAL_POINT",
            message=str(error),
        )
    expected = set(_expected_keys(origins, positions, policy))
    observed = set(actual)
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    passed = not missing and not unexpected
    return ContractCheck(
        name="historical_record_coverage",
        passed=passed,
        failure_class=None if passed else "HISTORICAL_ALIGNMENT_FAILED",
        message=None if passed else "historical forecast keys do not match policy",
        evidence={
            "expected_count": len(expected),
            "observed_count": len(observed),
            "missing": missing[:20],
            "unexpected": unexpected[:20],
        },
    )


def calculate_metrics(
    records: Sequence[HistoricalPoint],
    positions: Sequence[str],
    *,
    tolerance: float = 1.0,
) -> dict[str, Any]:
    if not records:
        raise ValueError("metric calculation requires historical points")
    ordered = sorted(records, key=lambda item: (item.origin, item.target_index, item.position))
    actual = np.asarray([item.actual for item in ordered], dtype=float)
    predicted = np.asarray([item.predicted for item in ordered], dtype=float)
    errors = predicted - actual
    absolute = np.abs(errors)
    squared = np.square(errors)
    hits = absolute <= tolerance
    position_hits: list[float] = []
    for position in positions:
        mask = np.asarray([item.position == position for item in ordered], dtype=bool)
        if not mask.any():
            raise ValueError(f"position is absent from records: {position}")
        position_hits.append(float(hits[mask].mean()))
    grouped_hits: dict[tuple[int, int], list[bool]] = {}
    for item, hit in zip(ordered, hits, strict=True):
        grouped_hits.setdefault((item.origin, item.target_index), []).append(bool(hit))
    all_position_hit = float(np.mean([all(values) for values in grouped_hits.values()]))
    return {
        "hit_at_plus_minus_1": float(hits.mean()),
        "position_hit_at_plus_minus_1": position_hits,
        "all_position_hit_at_plus_minus_1": all_position_hit,
        "mae": float(absolute.mean()),
        "mse": float(squared.mean()),
        "rmse": float(np.sqrt(squared.mean())),
        "point_count": int(actual.size),
        "forecast_group_count": len(grouped_hits),
        "tolerance": float(tolerance),
    }


def canonical_residuals(records: Sequence[HistoricalPoint]) -> tuple[float, ...]:
    ordered = sorted(records, key=lambda item: (item.origin, item.target_index, item.position))
    return tuple(float(item.actual - item.predicted) for item in ordered)


def summarize_residuals(residuals: Sequence[float]) -> dict[str, float]:
    array = np.asarray(residuals, dtype=float)
    if array.size == 0:
        raise ValueError("residual summary requires at least one value")
    if not np.isfinite(array).all():
        raise ValueError("residuals contain NaN or Inf")
    lag_one = 0.0
    if array.size > 1 and float(np.std(array)) > 0.0:
        lag_one = float(np.corrcoef(array[:-1], array[1:])[0, 1])
        if not np.isfinite(lag_one):
            lag_one = 0.0
    return {
        "count": float(array.size),
        "mean": float(array.mean()),
        "std": float(array.std(ddof=0)),
        "mae": float(np.abs(array).mean()),
        "max_abs": float(np.abs(array).max()),
        "median": float(np.median(array)),
        "lag1_autocorrelation": lag_one,
        "positive_fraction": float((array > 0.0).mean()),
        "negative_fraction": float((array < 0.0).mean()),
    }


def certify_retrain_schedule(
    origins: Sequence[int],
    policy: HistoricalForecastPolicy,
    evidence: HistoricalRuntimeEvidence,
) -> ContractCheck:
    expected = expected_fit_origins(origins, policy.retrain)
    observed = tuple(evidence.observed_fit_origins)
    if policy.retrain is False and policy.require_prefit_when_no_retrain:
        if not evidence.prefit:
            return ContractCheck(
                name="retrain_schedule",
                passed=False,
                failure_class="PREFIT_EVIDENCE_MISSING",
                message="retrain=False requires prefit evidence",
                evidence={"expected": list(expected), "observed": list(observed)},
            )
    passed = observed == expected
    return ContractCheck(
        name="retrain_schedule",
        passed=passed,
        failure_class=None if passed else "RETRAIN_SCHEDULE_MISMATCH",
        message=None if passed else "observed fit origins do not match retrain policy",
        evidence={"expected": list(expected), "observed": list(observed)},
    )


def certify_metric_parity(
    metrics: Mapping[str, Any],
    backtest_metrics: Mapping[str, float],
    policy: HistoricalForecastPolicy,
) -> ContractCheck:
    required = ("mae", "mse", "rmse")
    missing = [name for name in required if name not in backtest_metrics]
    if missing:
        return ContractCheck(
            name="backtest_metric_parity",
            passed=False,
            failure_class="BACKTEST_METRIC_MISSING",
            message=f"backtest result is missing metrics: {missing}",
        )
    deltas: dict[str, float] = {}
    failures: list[str] = []
    for name in required:
        expected = float(metrics[name])
        observed = float(backtest_metrics[name])
        deltas[name] = observed - expected
        if not np.isclose(
            observed,
            expected,
            rtol=policy.metric_rtol,
            atol=policy.metric_atol,
        ):
            failures.append(name)
    passed = not failures
    return ContractCheck(
        name="backtest_metric_parity",
        passed=passed,
        failure_class=None if passed else "BACKTEST_METRIC_MISMATCH",
        message=None if passed else f"metric parity failed for: {failures}",
        evidence={"deltas": deltas},
    )


def certify_residual_parity(
    records: Sequence[HistoricalPoint],
    runtime_residuals: Sequence[float],
    policy: HistoricalForecastPolicy,
) -> ContractCheck:
    expected = np.asarray(canonical_residuals(records), dtype=float)
    observed = np.asarray(runtime_residuals, dtype=float)
    shape_match = expected.shape == observed.shape
    passed = shape_match and bool(
        np.allclose(
            expected,
            observed,
            rtol=policy.residual_rtol,
            atol=policy.residual_atol,
        )
    )
    max_delta = None
    if shape_match and expected.size:
        max_delta = float(np.max(np.abs(expected - observed)))
    return ContractCheck(
        name="residual_parity",
        passed=passed,
        failure_class=None if passed else "RESIDUAL_PARITY_MISMATCH",
        message=None if passed else "Darts residuals differ from actual minus prediction",
        evidence={
            "expected_shape": list(expected.shape),
            "observed_shape": list(observed.shape),
            "max_abs_delta": max_delta,
        },
    )


def certify_optimization_parity(
    records: Sequence[HistoricalPoint],
    optimized_records: Sequence[HistoricalPoint] | None,
    policy: HistoricalForecastPolicy,
) -> ContractCheck:
    if not policy.compare_optimization:
        return ContractCheck(
            name="historical_optimization_parity",
            passed=True,
            evidence={"comparison_required": False},
        )
    if optimized_records is None:
        return ContractCheck(
            name="historical_optimization_parity",
            passed=False,
            failure_class="OPTIMIZATION_PARITY_EVIDENCE_MISSING",
            message="optimized and general historical forecasts must both be recorded",
        )
    left = _record_map(records)
    right = _record_map(optimized_records)
    if set(left) != set(right):
        return ContractCheck(
            name="historical_optimization_parity",
            passed=False,
            failure_class="OPTIMIZATION_ALIGNMENT_MISMATCH",
            message="optimized and general forecasts use different keys",
        )
    deltas = [abs(left[key].predicted - right[key].predicted) for key in sorted(left)]
    max_delta = float(max(deltas, default=0.0))
    passed = bool(
        np.allclose(
            [left[key].predicted for key in sorted(left)],
            [right[key].predicted for key in sorted(right)],
            rtol=policy.metric_rtol,
            atol=policy.metric_atol,
        )
    )
    return ContractCheck(
        name="historical_optimization_parity",
        passed=passed,
        failure_class=None if passed else "OPTIMIZATION_PREDICTION_MISMATCH",
        message=None if passed else "optimized and general forecasts differ",
        evidence={"max_abs_delta": max_delta},
    )


def _canonical_hash(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_contract_report(
    frame: pd.DataFrame,
    positions: Sequence[str],
    policy: HistoricalForecastPolicy,
    evidence: HistoricalRuntimeEvidence,
) -> HistoricalContractReport:
    original = frame.copy(deep=True)
    positions_tuple = tuple(positions)
    if not positions_tuple or len(set(positions_tuple)) != len(positions_tuple):
        raise ValueError("positions must be non-empty and unique")
    origins = expected_origins(len(frame), policy)
    coverage = validate_record_coverage(
        evidence.records,
        origins,
        positions_tuple,
        policy,
    )
    checks: list[ContractCheck] = [coverage]
    metrics: dict[str, Any] = {}
    residual_summary: dict[str, float] = {}
    if coverage.passed:
        metrics = calculate_metrics(evidence.records, positions_tuple)
        residual_summary = summarize_residuals(canonical_residuals(evidence.records))
        checks.extend(
            [
                certify_retrain_schedule(origins, policy, evidence),
                certify_metric_parity(metrics, evidence.backtest_metrics, policy),
                certify_residual_parity(evidence.records, evidence.residuals, policy),
                certify_optimization_parity(
                    evidence.records,
                    evidence.optimized_records,
                    policy,
                ),
            ]
        )
    pd.testing.assert_frame_equal(frame, original, check_exact=True)
    passed = all(check.passed for check in checks)
    record_payload = [
        record.model_dump(mode="json")
        for record in sorted(
            evidence.records,
            key=lambda item: (item.origin, item.target_index, item.position),
        )
    ]
    return HistoricalContractReport(
        status="HISTORICAL_EVIDENCE_CERTIFIED" if passed else "FAILED",
        expected_origins=origins,
        expected_fit_origins=expected_fit_origins(origins, policy.retrain),
        metrics=metrics,
        residual_summary=residual_summary,
        checks=tuple(checks),
        records_sha256=_canonical_hash(record_payload),
        policy_sha256=_canonical_hash(policy.model_dump(mode="json")),
    )


def _classify_call(
    method_name: str, function: Any, requested: Mapping[str, Any]
) -> tuple[
    dict[str, Any],
    ApiCallEvidence,
]:
    signature = inspect.signature(function)
    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    effective: dict[str, Any] = {}
    decisions: list[ApiArgumentDecision] = []
    rejected: list[str] = []
    for name, value in requested.items():
        if name in signature.parameters or accepts_var_kwargs:
            effective[name] = value
            decisions.append(
                ApiArgumentDecision(
                    method=method_name,
                    argument=name,
                    status="accepted",
                )
            )
        else:
            rejected.append(name)
            decisions.append(
                ApiArgumentDecision(
                    method=method_name,
                    argument=name,
                    status="rejected",
                    reason="argument is absent from runtime signature",
                )
            )
    evidence = ApiCallEvidence(
        method=method_name,
        requested_arguments=tuple(sorted(requested)),
        effective_arguments=tuple(sorted(effective)),
        decisions=tuple(decisions),
    )
    if rejected:
        raise ValueError(f"{method_name} rejected arguments: {sorted(rejected)}")
    return effective, evidence


def collect_darts_runtime_evidence(
    model: Any,
    series: Any,
    actual_frame: pd.DataFrame,
    positions: Sequence[str],
    policy: HistoricalForecastPolicy,
    *,
    metric_objects: Sequence[Any],
    record_normalizer: RecordNormalizer,
    backtest_normalizer: BacktestNormalizer,
    residual_normalizer: ResidualNormalizer,
    observed_fit_origins: Sequence[int] = (),
    prefit: bool = False,
) -> HistoricalRuntimeEvidence:
    historical_requested = {
        "series": series,
        "start": policy.start,
        "forecast_horizon": policy.forecast_horizon,
        "stride": policy.stride,
        "retrain": policy.retrain,
        "train_length": policy.train_length,
        "overlap_end": policy.overlap_end,
        "last_points_only": policy.last_points_only,
        "enable_optimization": False if policy.compare_optimization else policy.enable_optimization,
        **policy.historical_extra_args,
    }
    historical_args, historical_call = _classify_call(
        "historical_forecasts",
        model.historical_forecasts,
        historical_requested,
    )
    raw_historical = model.historical_forecasts(**historical_args)
    records = record_normalizer(
        raw_historical,
        actual_frame,
        tuple(positions),
        policy,
    )

    optimized_records: tuple[HistoricalPoint, ...] | None = None
    calls: list[ApiCallEvidence] = [historical_call]
    if policy.compare_optimization:
        optimized_requested = dict(historical_requested)
        optimized_requested["enable_optimization"] = True
        optimized_args, optimized_call = _classify_call(
            "historical_forecasts_optimized",
            model.historical_forecasts,
            optimized_requested,
        )
        raw_optimized = model.historical_forecasts(**optimized_args)
        optimized_records = record_normalizer(
            raw_optimized,
            actual_frame,
            tuple(positions),
            policy,
        )
        calls.append(optimized_call)

    backtest_requested = {
        "series": series,
        "historical_forecasts": raw_historical,
        "metric": list(metric_objects),
        **policy.backtest_extra_args,
    }
    backtest_args, backtest_call = _classify_call(
        "backtest",
        model.backtest,
        backtest_requested,
    )
    raw_backtest = model.backtest(**backtest_args)
    calls.append(backtest_call)

    residual_requested = {
        "series": series,
        "historical_forecasts": raw_historical,
        **policy.residual_extra_args,
    }
    residual_args, residual_call = _classify_call(
        "residuals",
        model.residuals,
        residual_requested,
    )
    raw_residuals = model.residuals(**residual_args)
    calls.append(residual_call)

    return HistoricalRuntimeEvidence(
        records=records,
        backtest_metrics=backtest_normalizer(raw_backtest),
        residuals=residual_normalizer(raw_residuals),
        observed_fit_origins=tuple(int(item) for item in observed_fit_origins),
        prefit=prefit,
        optimized_records=optimized_records,
        api_calls=tuple(calls),
    )
