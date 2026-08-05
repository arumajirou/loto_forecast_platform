from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest
from pydantic import ValidationError

from loto.darts_campaign.historical_evaluation import (
    HistoricalForecastPolicy,
    HistoricalPoint,
    HistoricalRuntimeEvidence,
    build_contract_report,
    calculate_metrics,
    canonical_residuals,
    certify_metric_parity,
    certify_optimization_parity,
    certify_residual_parity,
    collect_darts_runtime_evidence,
    expected_fit_origins,
    expected_origins,
)


POSITIONS = ("N1", "N2")


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": range(8),
            "N1": [1, 2, 3, 4, 5, 6, 7, 8],
            "N2": [2, 3, 4, 5, 6, 7, 8, 9],
        }
    )


def policy(**updates: object) -> HistoricalForecastPolicy:
    payload = {
        "start": 4,
        "forecast_horizon": 2,
        "stride": 2,
        "retrain": True,
        "last_points_only": True,
        "compare_optimization": True,
    }
    payload.update(updates)
    return HistoricalForecastPolicy(**payload)


def records(delta: float = 0.0) -> tuple[HistoricalPoint, ...]:
    output = []
    for origin in (4, 6):
        target = origin + 1
        for position, actual in zip(
            POSITIONS,
            (float(target + 1), float(target + 2)),
            strict=True,
        ):
            output.append(
                HistoricalPoint(
                    origin=origin,
                    target_index=target,
                    position=position,
                    actual=actual,
                    predicted=actual + delta,
                )
            )
    return tuple(output)


def evidence(
    *,
    points: tuple[HistoricalPoint, ...] | None = None,
    residuals: tuple[float, ...] | None = None,
    backtest: dict[str, float] | None = None,
    fits: tuple[int, ...] = (4, 6),
    optimized: tuple[HistoricalPoint, ...] | None = None,
    prefit: bool = False,
) -> HistoricalRuntimeEvidence:
    points = points or records(0.5)
    metrics = calculate_metrics(points, POSITIONS)
    return HistoricalRuntimeEvidence(
        records=points,
        backtest_metrics=backtest
        or {name: float(metrics[name]) for name in ("mae", "mse", "rmse")},
        residuals=residuals or canonical_residuals(points),
        observed_fit_origins=fits,
        prefit=prefit,
        optimized_records=optimized or points,
    )


def test_policy_rejects_override_and_invalid_retrain() -> None:
    with pytest.raises(ValidationError):
        policy(retrain=0)
    with pytest.raises(ValidationError):
        policy(historical_extra_args={"stride": 99})
    with pytest.raises(ValidationError):
        policy(overlap_end=True)


def test_expected_origins_are_complete_and_time_ordered() -> None:
    assert expected_origins(8, policy()) == (4, 6)
    assert expected_fit_origins((4, 6, 8, 10), True) == (4, 6, 8, 10)
    assert expected_fit_origins((4, 6, 8, 10), False) == ()
    assert expected_fit_origins((4, 6, 8, 10), 2) == (4, 8)


def test_metrics_include_primary_and_position_contracts() -> None:
    result = calculate_metrics(records(0.5), POSITIONS)
    assert result["hit_at_plus_minus_1"] == 1.0
    assert result["position_hit_at_plus_minus_1"] == [1.0, 1.0]
    assert result["all_position_hit_at_plus_minus_1"] == 1.0
    assert result["mae"] == 0.5
    assert result["mse"] == 0.25
    assert result["rmse"] == 0.5


def test_backtest_metric_parity_is_fail_closed() -> None:
    points = records(0.5)
    metrics = calculate_metrics(points, POSITIONS)
    ok = certify_metric_parity(
        metrics,
        {name: float(metrics[name]) for name in ("mae", "mse", "rmse")},
        policy(),
    )
    assert ok.passed
    failed = certify_metric_parity(
        metrics,
        {"mae": 9.0, "mse": 9.0, "rmse": 3.0},
        policy(),
    )
    assert not failed.passed
    assert failed.failure_class == "BACKTEST_METRIC_MISMATCH"


def test_residual_parity_detects_sign_mismatch() -> None:
    points = records(0.5)
    ok = certify_residual_parity(points, canonical_residuals(points), policy())
    assert ok.passed
    wrong = tuple(-item for item in canonical_residuals(points))
    failed = certify_residual_parity(points, wrong, policy())
    assert not failed.passed
    assert failed.failure_class == "RESIDUAL_PARITY_MISMATCH"


def test_optimization_parity_detects_prediction_drift() -> None:
    ok = certify_optimization_parity(records(0.5), records(0.5), policy())
    assert ok.passed
    failed = certify_optimization_parity(records(0.5), records(0.6), policy())
    assert not failed.passed
    assert failed.failure_class == "OPTIMIZATION_PREDICTION_MISMATCH"


def test_report_rejects_missing_record_and_preserves_frame() -> None:
    source = frame()
    before = source.copy(deep=True)
    broken = records(0.5)[:-1]
    report = build_contract_report(
        source,
        POSITIONS,
        policy(),
        evidence(points=broken, optimized=broken),
    )
    assert report.status == "FAILED"
    assert report.checks[0].failure_class == "HISTORICAL_ALIGNMENT_FAILED"
    pd.testing.assert_frame_equal(source, before, check_exact=True)


def test_retrain_false_requires_prefit_evidence() -> None:
    current = policy(retrain=False)
    failed = build_contract_report(
        frame(),
        POSITIONS,
        current,
        evidence(fits=(), prefit=False),
    )
    assert failed.status == "FAILED"
    assert any(
        check.failure_class == "PREFIT_EVIDENCE_MISSING"
        for check in failed.checks
    )
    passed = build_contract_report(
        frame(),
        POSITIONS,
        current,
        evidence(fits=(), prefit=True),
    )
    assert passed.status == "HISTORICAL_EVIDENCE_CERTIFIED"


def test_integer_retrain_schedule_is_verified_exactly() -> None:
    current = policy(stride=1, retrain=2)
    points = []
    for origin in (4, 5, 6):
        target = origin + 1
        for position, actual in zip(
            POSITIONS,
            (target + 1.0, target + 2.0),
            strict=True,
        ):
            points.append(
                HistoricalPoint(
                    origin=origin,
                    target_index=target,
                    position=position,
                    actual=actual,
                    predicted=actual,
                )
            )
    point_tuple = tuple(points)
    metric_values = calculate_metrics(point_tuple, POSITIONS)
    runtime = HistoricalRuntimeEvidence(
        records=point_tuple,
        backtest_metrics={
            name: float(metric_values[name]) for name in ("mae", "mse", "rmse")
        },
        residuals=canonical_residuals(point_tuple),
        observed_fit_origins=(4, 6),
        optimized_records=point_tuple,
    )
    report = build_contract_report(frame(), POSITIONS, current, runtime)
    assert report.status == "HISTORICAL_EVIDENCE_CERTIFIED"
    assert report.expected_fit_origins == (4, 6)


def test_hashes_are_stable_and_tamper_sensitive() -> None:
    report_a = build_contract_report(frame(), POSITIONS, policy(), evidence())
    report_b = build_contract_report(frame(), POSITIONS, policy(), evidence())
    report_c = build_contract_report(
        frame(),
        POSITIONS,
        policy(),
        evidence(points=records(0.6), optimized=records(0.6)),
    )
    assert report_a.records_sha256 == report_b.records_sha256
    assert report_a.records_sha256 != report_c.records_sha256
    assert report_a.policy_sha256 == report_b.policy_sha256


class FakeModel:
    def __init__(self, raw_records: tuple[HistoricalPoint, ...]) -> None:
        self.raw_records = raw_records
        self.calls: list[tuple[str, dict[str, object]]] = []

    def historical_forecasts(
        self,
        series: object,
        start: int,
        forecast_horizon: int,
        stride: int,
        retrain: bool | int,
        train_length: int | None,
        overlap_end: bool,
        last_points_only: bool,
        enable_optimization: bool,
    ) -> tuple[HistoricalPoint, ...]:
        self.calls.append(("historical_forecasts", deepcopy(locals())))
        return self.raw_records

    def backtest(
        self,
        series: object,
        historical_forecasts: tuple[HistoricalPoint, ...],
        metric: list[object],
    ) -> dict[str, float]:
        self.calls.append(("backtest", deepcopy(locals())))
        values = calculate_metrics(historical_forecasts, POSITIONS)
        return {name: float(values[name]) for name in ("mae", "mse", "rmse")}

    def residuals(
        self,
        series: object,
        historical_forecasts: tuple[HistoricalPoint, ...],
    ) -> tuple[float, ...]:
        self.calls.append(("residuals", deepcopy(locals())))
        return canonical_residuals(historical_forecasts)


def test_runtime_collection_calls_all_three_darts_apis() -> None:
    model = FakeModel(records(0.5))
    runtime = collect_darts_runtime_evidence(
        model,
        series=object(),
        actual_frame=frame(),
        positions=POSITIONS,
        policy=policy(),
        metric_objects=(object(), object(), object()),
        record_normalizer=lambda raw, _frame, _positions, _policy: raw,
        backtest_normalizer=lambda raw: raw,
        residual_normalizer=lambda raw: raw,
        observed_fit_origins=(4, 6),
    )
    assert [call[0] for call in model.calls] == [
        "historical_forecasts",
        "historical_forecasts",
        "backtest",
        "residuals",
    ]
    assert [call.method for call in runtime.api_calls] == [
        "historical_forecasts",
        "historical_forecasts_optimized",
        "backtest",
        "residuals",
    ]
    report = build_contract_report(frame(), POSITIONS, policy(), runtime)
    assert report.status == "HISTORICAL_EVIDENCE_CERTIFIED"


def test_runtime_collection_rejects_unknown_arguments_without_drop() -> None:
    model = FakeModel(records(0.5))
    current = policy(backtest_extra_args={"unsupported": 1})
    with pytest.raises(ValueError, match="backtest rejected arguments"):
        collect_darts_runtime_evidence(
            model,
            series=object(),
            actual_frame=frame(),
            positions=POSITIONS,
            policy=current,
            metric_objects=(object(),),
            record_normalizer=lambda raw, _frame, _positions, _policy: raw,
            backtest_normalizer=lambda raw: raw,
            residual_normalizer=lambda raw: raw,
        )
