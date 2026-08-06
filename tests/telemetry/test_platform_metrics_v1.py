from __future__ import annotations

import math
from itertools import product

import pytest
from prometheus_client import REGISTRY, CollectorRegistry
from pydantic import ValidationError

from loto.telemetry import EventStatus, MetricKind, PROHIBITED_LABELS, Stage
from loto.telemetry.prometheus import (
    MetricUpdate,
    PrometheusMetricSet,
    default_platform_metric_catalog,
    horizon_label,
)

REQUIRED_NAMES = {
    "loto_telemetry_events_total",
    "loto_telemetry_dropped_total",
    "loto_telemetry_buffer_size",
    "loto_pipeline_runs_total",
    "loto_pipeline_stage_duration_seconds",
    "loto_pipeline_active_runs",
    "loto_pipeline_last_success_timestamp_seconds",
    "loto_model_inference_total",
    "loto_model_inference_duration_seconds",
    "loto_model_load_duration_seconds",
    "loto_model_cpu_fallback_total",
    "loto_model_output_nonfinite_total",
    "loto_model_replay_mismatch_total",
    "loto_evaluation_runs_total",
    "loto_evaluation_hit_at_1",
    "loto_evaluation_all_positions_hit_at_1",
    "loto_evaluation_mae",
    "loto_evaluation_worst_seed_hit_at_1",
    "loto_evaluation_protocol_mismatch_total",
    "loto_evaluation_leakage_sentinel_total",
    "loto_data_rows",
    "loto_data_last_observation_timestamp_seconds",
    "loto_data_missing_values",
    "loto_data_duplicate_rows",
    "loto_data_order_violations_total",
    "loto_data_future_access_blocked_total",
    "loto_registry_operations_total",
    "loto_artifact_integrity_failure_total",
    "loto_prediction_lock_verification_total",
}


def test_catalog_contains_exact_required_metric_families() -> None:
    catalog = default_platform_metric_catalog()
    assert {spec.definition.name for spec in catalog.specs()} == REQUIRED_NAMES


def test_catalog_does_not_redeclare_pr127_health_metric_names() -> None:
    catalog = default_platform_metric_catalog()
    names = {spec.definition.name for spec in catalog.specs()}
    health_names = {
        "loto_health_endpoint_requests_total",
        "loto_dependency_probe_total",
        "loto_dependency_ready",
        "loto_dependency_probe_duration_seconds",
        "loto_api_readiness_status",
    }
    assert names.isdisjoint(health_names)


def test_all_labels_are_finite_and_prohibited_labels_are_absent() -> None:
    catalog = default_platform_metric_catalog()
    for spec in catalog.specs():
        labels = spec.definition.label_allowlist
        assert not (set(labels) & PROHIBITED_LABELS)
        assert len(labels) <= 5
        for values in labels.values():
            assert values
            assert len(values) <= 64
            assert len(values) == len(set(values))


def test_catalog_cardinality_bound_is_deterministic_and_below_budget() -> None:
    catalog = default_platform_metric_catalog()
    first = catalog.total_series_upper_bound()
    second = default_platform_metric_catalog().total_series_upper_bound()
    assert first == second
    assert first < 25_000
    maximum = max(
        catalog.series_upper_bound(spec.definition.name)
        for spec in catalog.specs()
    )
    assert maximum < 5_000
    with pytest.raises(ValueError, match="exceeds"):
        catalog.assert_budget(maximum_total_series=1, maximum_metric_series=5_000)


def test_isolated_registries_do_not_touch_global_registry_or_collide() -> None:
    before = {family.name for family in REGISTRY.collect()}
    one = PrometheusMetricSet(registry=CollectorRegistry())
    two = PrometheusMetricSet(registry=CollectorRegistry())
    assert one.registry is not two.registry
    assert {family.name for family in REGISTRY.collect()} == before


def test_counter_gauge_and_histogram_render_with_approved_labels() -> None:
    metrics = PrometheusMetricSet()
    metrics.increment(
        "loto_pipeline_runs_total",
        labels={"stage": Stage.PREDICT.value, "status": EventStatus.PASS.value},
    )
    metrics.set_gauge(
        "loto_evaluation_hit_at_1",
        0.75,
        labels={"game": "numbers4", "position": "N1", "split": "validation"},
    )
    metrics.observe(
        "loto_model_inference_duration_seconds",
        0.125,
        labels={"provider": "neuralforecast", "device": "cuda", "horizon": "1"},
    )
    rendered = metrics.render().decode()
    assert 'loto_pipeline_runs_total{stage="PREDICT",status="PASS"} 1.0' in rendered
    expected = (
        'loto_evaluation_hit_at_1{game="numbers4",position="N1",'
        'split="validation"} 0.75'
    )
    assert expected in rendered
    assert "loto_model_inference_duration_seconds_count" in rendered


def test_unknown_missing_extra_or_prohibited_label_values_are_rejected() -> None:
    metrics = PrometheusMetricSet()
    with pytest.raises(KeyError, match="unknown platform metric"):
        metrics.increment("loto_missing_total")
    with pytest.raises(ValueError):
        metrics.increment("loto_pipeline_runs_total", labels={"stage": "PREDICT"})
    with pytest.raises(ValueError):
        metrics.increment(
            "loto_pipeline_runs_total",
            labels={"stage": "PREDICT", "status": "PASS", "run_id": "run-1"},
        )
    with pytest.raises(ValueError):
        metrics.increment(
            "loto_model_cpu_fallback_total",
            labels={"provider": "unbounded-provider"},
        )


def test_position_labels_follow_game_geometry() -> None:
    metrics = PrometheusMetricSet()
    with pytest.raises(ValueError, match="invalid for game numbers3"):
        metrics.set_gauge(
            "loto_evaluation_hit_at_1",
            0.5,
            labels={
                "game": "numbers3",
                "position": "N4",
                "split": "validation",
            },
        )
    metrics.set_gauge(
        "loto_evaluation_hit_at_1",
        0.5,
        labels={
            "game": "numbers3",
            "position": "N3",
            "split": "validation",
        },
    )


def test_metric_kind_and_value_policies_are_fail_closed() -> None:
    metrics = PrometheusMetricSet()
    labels = {"game": "numbers4", "position": "N1", "split": "validation"}
    with pytest.raises(ValueError, match="not gauge"):
        metrics.set_gauge(
            "loto_pipeline_runs_total",
            1,
            labels={"stage": "PREDICT", "status": "PASS"},
        )
    with pytest.raises(ValueError, match="minimum"):
        metrics.increment(
            "loto_model_cpu_fallback_total",
            -1,
            labels={"provider": "builtin"},
        )
    with pytest.raises(ValueError, match="maximum"):
        metrics.set_gauge("loto_evaluation_hit_at_1", 1.01, labels=labels)
    with pytest.raises(ValueError, match="integer"):
        metrics.set_gauge(
            "loto_data_rows",
            1.5,
            labels={"game": "numbers4", "role": "raw"},
        )
    with pytest.raises(ValueError, match="finite"):
        metrics.observe(
            "loto_model_load_duration_seconds",
            math.inf,
            labels={"provider": "builtin", "device": "cpu"},
        )


def test_metric_update_is_strict_and_batch_validates_before_mutation() -> None:
    metrics = PrometheusMetricSet()
    good = MetricUpdate(
        name="loto_model_cpu_fallback_total",
        value=1.0,
        labels={"provider": "builtin"},
    )
    bad = MetricUpdate(
        name="loto_model_cpu_fallback_total",
        value=1.0,
        labels={"provider": "not-approved"},
    )
    before = metrics.render()
    with pytest.raises(ValueError):
        metrics.apply_updates(
            ((MetricKind.COUNTER, good), (MetricKind.COUNTER, bad))
        )
    assert metrics.render() == before
    with pytest.raises(ValidationError):
        MetricUpdate(name="x", value="1", labels={})


def test_histogram_buckets_are_reviewed_unique_and_increasing() -> None:
    catalog = default_platform_metric_catalog()
    histograms = [
        spec.definition
        for spec in catalog.specs()
        if spec.definition.kind is MetricKind.HISTOGRAM
    ]
    assert {item.name for item in histograms} == {
        "loto_pipeline_stage_duration_seconds",
        "loto_model_inference_duration_seconds",
        "loto_model_load_duration_seconds",
    }
    for definition in histograms:
        assert definition.buckets == tuple(sorted(set(definition.buckets)))
        assert definition.buckets[0] > 0


def test_horizon_bucket_is_bounded() -> None:
    assert horizon_label(1) == "1"
    assert horizon_label(7) == "2_7"
    assert horizon_label(8) == "8_31"
    assert horizon_label(31) == "8_31"
    assert horizon_label(32) == "32_plus"
    with pytest.raises(ValueError):
        horizon_label(0)
    with pytest.raises(ValueError):
        horizon_label(True)


def test_touched_series_are_lazy_not_preinitialized_for_all_combinations() -> None:
    metrics = PrometheusMetricSet()
    baseline = metrics.touched_series_count()
    # The intentionally unlabeled telemetry buffer gauge is exported at zero.
    assert baseline == 1
    metrics.increment("loto_model_cpu_fallback_total", labels={"provider": "builtin"})
    assert metrics.touched_series_count() > baseline
    assert (
        metrics.touched_series_count()
        < metrics.catalog.total_series_upper_bound()
    )


def test_full_allowlist_stress_stays_within_declared_series_budget() -> None:
    metrics = PrometheusMetricSet()
    for spec in metrics.catalog.specs():
        definition = spec.definition
        label_names = tuple(definition.label_allowlist)
        value_sets = tuple(definition.label_allowlist[name] for name in label_names)
        combinations = product(*value_sets) if value_sets else ((),)
        for values in combinations:
            labels = dict(zip(label_names, values, strict=True))
            try:
                metrics.catalog.validate_labels(definition.name, labels)
            except ValueError as exc:
                if "invalid for game" in str(exc):
                    continue
                raise
            if definition.kind is MetricKind.COUNTER:
                metrics.increment(definition.name, 1, labels=labels)
            elif definition.kind is MetricKind.GAUGE:
                metrics.set_gauge(definition.name, 1, labels=labels)
            else:
                metrics.observe(definition.name, 0.01, labels=labels)
    assert (
        metrics.touched_series_count()
        <= metrics.catalog.total_series_upper_bound()
    )
