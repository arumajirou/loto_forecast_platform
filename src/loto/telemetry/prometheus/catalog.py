"""Bounded platform metric catalog built on the exporter-neutral registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import prod
from typing import Final

from loto.telemetry.contracts import EventStatus, Stage
from loto.telemetry.metrics import (
    MetricDefinition,
    MetricKind,
    MetricRegistry,
    default_telemetry_metric_registry,
)


class GameLabel(StrEnum):
    NUMBERS3 = "numbers3"
    NUMBERS4 = "numbers4"
    MINILOTO = "miniloto"
    LOTO6 = "loto6"
    LOTO7 = "loto7"
    UNKNOWN = "unknown"


class DeviceLabel(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"
    XPU = "xpu"
    UNKNOWN = "unknown"


class SplitLabel(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    HOLDOUT = "holdout"
    PROSPECTIVE = "prospective"


class HorizonLabel(StrEnum):
    ONE = "1"
    TWO_TO_SEVEN = "2_7"
    EIGHT_TO_THIRTY_ONE = "8_31"
    THIRTY_TWO_PLUS = "32_plus"


PROVIDER_LABELS: Final[tuple[str, ...]] = (
    "neuralforecast",
    "statsforecast",
    "mlforecast",
    "hierarchicalforecast",
    "sktime",
    "darts",
    "gluonts",
    "timeseries_library",
    "basicts",
    "tsfm",
    "sklearn",
    "builtin",
    "unknown",
)
POSITION_LABELS: Final[tuple[str, ...]] = (
    "N1",
    "N2",
    "N3",
    "N4",
    "N5",
    "N6",
    "N7",
)
GAME_POSITION_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    "numbers3": frozenset({"N1", "N2", "N3"}),
    "numbers4": frozenset({"N1", "N2", "N3", "N4"}),
    "miniloto": frozenset({"N1", "N2", "N3", "N4", "N5"}),
    "loto6": frozenset({"N1", "N2", "N3", "N4", "N5", "N6"}),
    "loto7": frozenset(POSITION_LABELS),
    "unknown": frozenset(POSITION_LABELS),
}
RESULT_LABELS: Final[tuple[str, ...]] = ("pass", "fail", "blocked")
DATA_ROLE_LABELS: Final[tuple[str, ...]] = (
    "raw",
    "normalized",
    "train",
    "validation",
    "holdout",
    "prospective",
)
COLUMN_GROUP_LABELS: Final[tuple[str, ...]] = (
    "identity",
    "target",
    "feature",
    "exogenous",
    "metadata",
    "unknown",
)
REGISTRY_OPERATION_LABELS: Final[tuple[str, ...]] = (
    "create",
    "read",
    "update",
    "delete",
    "promote",
    "rollback",
    "verify",
)
ARTIFACT_TYPE_LABELS: Final[tuple[str, ...]] = (
    "prediction",
    "model",
    "metrics",
    "manifest",
    "log",
    "report",
    "config",
    "dataset",
    "unknown",
)
PIPELINE_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    300.0,
    900.0,
    3600.0,
)
INFERENCE_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)
MODEL_LOAD_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    300.0,
    900.0,
)


@dataclass(frozen=True, slots=True)
class MetricValuePolicy:
    minimum: float | None = 0.0
    maximum: float | None = None
    integer_only: bool = False


@dataclass(frozen=True, slots=True)
class PlatformMetricSpec:
    definition: MetricDefinition
    value_policy: MetricValuePolicy = MetricValuePolicy()


class PlatformMetricCatalog:
    def __init__(self, specs: tuple[PlatformMetricSpec, ...]) -> None:
        registry = MetricRegistry()
        by_name: dict[str, PlatformMetricSpec] = {}
        for spec in specs:
            registry.register(spec.definition)
            by_name[spec.definition.name] = spec
        self._registry = registry
        self._by_name = by_name

    def get(self, name: str) -> PlatformMetricSpec:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"unknown platform metric: {name}") from exc

    def specs(self) -> tuple[PlatformMetricSpec, ...]:
        return tuple(self._by_name[name] for name in sorted(self._by_name))

    def validate_labels(self, name: str, labels: dict[str, str]) -> None:
        self._registry.validate_labels(name, labels)
        if name in {"loto_evaluation_hit_at_1", "loto_evaluation_mae"}:
            game = labels["game"]
            position = labels["position"]
            if position not in GAME_POSITION_ALLOWLIST[game]:
                raise ValueError(
                    f"metric {name} position {position} is invalid for game {game}"
                )

    def series_upper_bound(self, name: str) -> int:
        definition = self.get(name).definition
        label_product = prod(
            len(values) for values in definition.label_allowlist.values()
        )
        if not definition.label_allowlist:
            label_product = 1
        if definition.kind is MetricKind.COUNTER:
            multiplier = 2  # value plus the Python client's created timestamp
        elif definition.kind is MetricKind.HISTOGRAM:
            # Reviewed buckets, +Inf, count, sum, and created timestamp.
            multiplier = len(definition.buckets) + 4
        else:
            multiplier = 1
        return label_product * multiplier

    def total_series_upper_bound(self) -> int:
        return sum(
            self.series_upper_bound(spec.definition.name) for spec in self.specs()
        )

    def assert_budget(
        self,
        *,
        maximum_total_series: int,
        maximum_metric_series: int,
    ) -> None:
        if maximum_total_series < 1 or maximum_metric_series < 1:
            raise ValueError("series budgets must be positive")
        total = self.total_series_upper_bound()
        if total > maximum_total_series:
            raise ValueError(
                f"catalog series bound {total} exceeds {maximum_total_series}"
            )
        offenders = {
            spec.definition.name: self.series_upper_bound(spec.definition.name)
            for spec in self.specs()
            if self.series_upper_bound(spec.definition.name)
            > maximum_metric_series
        }
        if offenders:
            raise ValueError(f"per-metric series bound exceeded: {offenders}")


def _labels(**values: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    return values


def _spec(
    name: str,
    kind: MetricKind,
    description: str,
    unit: str,
    *,
    labels: dict[str, tuple[str, ...]] | None = None,
    buckets: tuple[float, ...] = (),
    minimum: float | None = 0.0,
    maximum: float | None = None,
    integer_only: bool = False,
) -> PlatformMetricSpec:
    return PlatformMetricSpec(
        definition=MetricDefinition(
            name=name,
            kind=kind,
            description=description,
            unit=unit,
            label_allowlist=labels or {},
            buckets=buckets,
        ),
        value_policy=MetricValuePolicy(minimum, maximum, integer_only),
    )


def _platform_specs(
    *,
    status: tuple[str, ...],
    stage: tuple[str, ...],
    game: tuple[str, ...],
    device: tuple[str, ...],
    split: tuple[str, ...],
    horizon: tuple[str, ...],
) -> tuple[PlatformMetricSpec, ...]:
    return (
        _spec(
            "loto_pipeline_runs_total",
            MetricKind.COUNTER,
            "Pipeline runs by stage and bounded status.",
            "runs",
            labels=_labels(stage=stage, status=status),
            integer_only=True,
        ),
        _spec(
            "loto_pipeline_stage_duration_seconds",
            MetricKind.HISTOGRAM,
            "Pipeline stage duration in seconds.",
            "seconds",
            labels=_labels(stage=stage, status=status),
            buckets=PIPELINE_DURATION_BUCKETS,
        ),
        _spec(
            "loto_pipeline_active_runs",
            MetricKind.GAUGE,
            "Current active pipeline runs by stage.",
            "runs",
            labels=_labels(stage=stage),
            integer_only=True,
        ),
        _spec(
            "loto_pipeline_last_success_timestamp_seconds",
            MetricKind.GAUGE,
            "Unix timestamp of the latest successful stage completion.",
            "seconds",
            labels=_labels(stage=stage),
        ),
        _spec(
            "loto_model_inference_total",
            MetricKind.COUNTER,
            "Model inference attempts by provider, status and device.",
            "inferences",
            labels=_labels(
                provider=PROVIDER_LABELS,
                status=status,
                device=device,
            ),
            integer_only=True,
        ),
        _spec(
            "loto_model_inference_duration_seconds",
            MetricKind.HISTOGRAM,
            "Model inference duration in seconds.",
            "seconds",
            labels=_labels(
                provider=PROVIDER_LABELS,
                device=device,
                horizon=horizon,
            ),
            buckets=INFERENCE_DURATION_BUCKETS,
        ),
        _spec(
            "loto_model_load_duration_seconds",
            MetricKind.HISTOGRAM,
            "Model load duration in seconds.",
            "seconds",
            labels=_labels(provider=PROVIDER_LABELS, device=device),
            buckets=MODEL_LOAD_DURATION_BUCKETS,
        ),
        _spec(
            "loto_model_cpu_fallback_total",
            MetricKind.COUNTER,
            "CPU fallbacks by provider.",
            "fallbacks",
            labels=_labels(provider=PROVIDER_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_model_output_nonfinite_total",
            MetricKind.COUNTER,
            "Non-finite model outputs by provider.",
            "outputs",
            labels=_labels(provider=PROVIDER_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_model_replay_mismatch_total",
            MetricKind.COUNTER,
            "Deterministic replay mismatches by provider.",
            "mismatches",
            labels=_labels(provider=PROVIDER_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_evaluation_runs_total",
            MetricKind.COUNTER,
            "Evaluation runs by game and status.",
            "runs",
            labels=_labels(game=game, status=status),
            integer_only=True,
        ),
        _spec(
            "loto_evaluation_hit_at_1",
            MetricKind.GAUGE,
            "Position-level Hit at plus or minus one.",
            "ratio",
            labels=_labels(
                game=game,
                position=POSITION_LABELS,
                split=split,
            ),
            maximum=1.0,
        ),
        _spec(
            "loto_evaluation_all_positions_hit_at_1",
            MetricKind.GAUGE,
            "All-position Hit at plus or minus one.",
            "ratio",
            labels=_labels(game=game, split=split),
            maximum=1.0,
        ),
        _spec(
            "loto_evaluation_mae",
            MetricKind.GAUGE,
            "Position-level mean absolute error.",
            "value",
            labels=_labels(
                game=game,
                position=POSITION_LABELS,
                split=split,
            ),
        ),
        _spec(
            "loto_evaluation_worst_seed_hit_at_1",
            MetricKind.GAUGE,
            "Worst approved-seed Hit at plus or minus one.",
            "ratio",
            labels=_labels(game=game, split=split),
            maximum=1.0,
        ),
        _spec(
            "loto_evaluation_protocol_mismatch_total",
            MetricKind.COUNTER,
            "Evaluation protocol comparison refusals by game.",
            "mismatches",
            labels=_labels(game=game),
            integer_only=True,
        ),
        _spec(
            "loto_evaluation_leakage_sentinel_total",
            MetricKind.COUNTER,
            "Leakage sentinel outcomes by game and result.",
            "checks",
            labels=_labels(game=game, result=RESULT_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_data_rows",
            MetricKind.GAUGE,
            "Rows in the latest immutable data snapshot by game and role.",
            "rows",
            labels=_labels(game=game, role=DATA_ROLE_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_data_last_observation_timestamp_seconds",
            MetricKind.GAUGE,
            "Unix timestamp of the latest observation by game.",
            "seconds",
            labels=_labels(game=game),
        ),
        _spec(
            "loto_data_missing_values",
            MetricKind.GAUGE,
            "Missing values by game and bounded column group.",
            "values",
            labels=_labels(game=game, column_group=COLUMN_GROUP_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_data_duplicate_rows",
            MetricKind.GAUGE,
            "Duplicate row count by game.",
            "rows",
            labels=_labels(game=game),
            integer_only=True,
        ),
        _spec(
            "loto_data_order_violations_total",
            MetricKind.COUNTER,
            "Chronological order violations by game.",
            "violations",
            labels=_labels(game=game),
            integer_only=True,
        ),
        _spec(
            "loto_data_future_access_blocked_total",
            MetricKind.COUNTER,
            "Blocked future-data access attempts by stage.",
            "attempts",
            labels=_labels(stage=stage),
            integer_only=True,
        ),
        _spec(
            "loto_registry_operations_total",
            MetricKind.COUNTER,
            "Registry operations by operation and status.",
            "operations",
            labels=_labels(
                operation=REGISTRY_OPERATION_LABELS,
                status=status,
            ),
            integer_only=True,
        ),
        _spec(
            "loto_artifact_integrity_failure_total",
            MetricKind.COUNTER,
            "Artifact integrity failures by bounded artifact type.",
            "failures",
            labels=_labels(artifact_type=ARTIFACT_TYPE_LABELS),
            integer_only=True,
        ),
        _spec(
            "loto_prediction_lock_verification_total",
            MetricKind.COUNTER,
            "Prediction lock verification outcomes.",
            "checks",
            labels=_labels(status=status),
            integer_only=True,
        ),
    )


def default_platform_metric_catalog() -> PlatformMetricCatalog:
    status = tuple(item.value for item in EventStatus)
    stage = tuple(item.value for item in Stage)
    game = tuple(item.value for item in GameLabel)
    device = tuple(item.value for item in DeviceLabel)
    split = tuple(item.value for item in SplitLabel)
    horizon = tuple(item.value for item in HorizonLabel)
    specs = [
        PlatformMetricSpec(item)
        for item in default_telemetry_metric_registry().definitions()
    ]
    specs.extend(
        _platform_specs(
            status=status,
            stage=stage,
            game=game,
            device=device,
            split=split,
            horizon=horizon,
        )
    )
    catalog = PlatformMetricCatalog(tuple(specs))
    catalog.assert_budget(
        maximum_total_series=25_000,
        maximum_metric_series=5_000,
    )
    return catalog


def horizon_label(horizon: int) -> str:
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if horizon == 1:
        return HorizonLabel.ONE.value
    if horizon <= 7:
        return HorizonLabel.TWO_TO_SEVEN.value
    if horizon <= 31:
        return HorizonLabel.EIGHT_TO_THIRTY_ONE.value
    return HorizonLabel.THIRTY_TWO_PLUS.value
