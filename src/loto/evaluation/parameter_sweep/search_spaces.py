"""Bounded, provenance-bearing coarse search spaces for the Bingo5 pilot."""

from __future__ import annotations

from typing import Any

from .contracts import (
    ModelInventoryRow,
    ModelSearchSpace,
    SearchDimension,
    SearchSpaceStatus,
)
from .routing import known_route_reason

_ALPHA_VALUES = (0.1, 0.3, 0.5, 0.7, 0.9)
_LAG_CANDIDATES = (1, 2, 3, 4, 5, 7, 14, 28)
_SEASON_CANDIDATES = (1, 2, 4, 7, 14)
_WINDOW_CANDIDATES = (2, 3, 4, 7, 14, 28)
_TEST_SIZE_CANDIDATES = (4, 8, 12, 20)
_RUNTIME_RESOLVED_REQUIRED: dict[str, set[str]] = {
    "neuralforecast": {"h", "input_size", "loss", "max_steps", "random_seed"},
    "neuralforecast_auto": {"h"},
    "mlforecast": set(),
    "statsforecast": set(),
}


def _bounded_ints(values: tuple[int, ...], upper: int) -> tuple[int, ...]:
    filtered = tuple(value for value in values if 0 < value <= upper)
    if len(filtered) >= 2:
        return filtered
    fallback = tuple(sorted({1, max(2, upper)}))
    return fallback if len(fallback) >= 2 else (1, 2)


def _dimension(name: str, *, train_rows: int) -> SearchDimension | None:
    if name in {"alpha", "alpha_d", "alpha_p"}:
        return SearchDimension(
            parameter=name,
            values=_ALPHA_VALUES,
            rationale=(
                "coarse interior scan of a bounded smoothing coefficient; includes the existing "
                "StatsForecast certification anchor 0.3 without treating it as the only valid value"
            ),
            provenance=(
                "installed constructor signature",
                "src/loto/statsforecast/certification_models.py",
                "Bingo5 pilot bounded-search policy",
            ),
        )
    if name == "lags":
        upper = max(2, min(28, train_rows // 10))
        return SearchDimension(
            parameter=name,
            values=_bounded_ints(_LAG_CANDIDATES, upper),
            rationale=(
                "short-to-medium autoregressive memory, bounded to at most one tenth of the "
                "available training history"
            ),
            provenance=(
                "installed constructor signature",
                "Bingo5 train-row bound",
                "operator-approved coarse lag candidates",
            ),
        )
    if name == "season_length":
        upper = max(2, min(14, train_rows // 4))
        return SearchDimension(
            parameter=name,
            values=_bounded_ints(_SEASON_CANDIDATES, upper),
            rationale=(
                "model hyperparameter comparison only; values do not assert real-world lottery "
                "seasonality and are bounded by training-history length"
            ),
            provenance=(
                "installed constructor signature",
                "src/loto/statsforecast/certification_models.py",
                "Bingo5 train-row bound",
            ),
        )
    if name == "window_size":
        upper = max(2, min(28, train_rows // 10))
        return SearchDimension(
            parameter=name,
            values=_bounded_ints(_WINDOW_CANDIDATES, upper),
            rationale="bounded short/medium moving-history windows relative to training history",
            provenance=(
                "installed constructor signature",
                "src/loto/statsforecast/certification_models.py",
                "Bingo5 train-row bound",
            ),
        )
    if name == "test_size":
        upper = max(4, min(20, train_rows // 4))
        return SearchDimension(
            parameter=name,
            values=_bounded_ints(_TEST_SIZE_CANDIDATES, upper),
            rationale="AutoMFLES internal validation size bounded by the available training history",
            provenance=(
                "installed constructor signature",
                "src/loto/statsforecast/certification_models.py",
                "Bingo5 train-row bound",
            ),
        )
    return None


def _baseline_params(row: ModelInventoryRow) -> dict[str, Any]:
    baseline = dict(row.current_default_params)
    for key, value in row.certification_params.items():
        baseline.setdefault(key, value)
    return baseline


def _closed_space(
    row: ModelInventoryRow,
    status: SearchSpaceStatus,
    reason: str,
    *,
    unresolved: tuple[str, ...] = (),
) -> ModelSearchSpace:
    return ModelSearchSpace(
        model_id=row.model_id,
        status=status,
        baseline_params=_baseline_params(row),
        unresolved_parameters=unresolved,
        reason=reason,
    )


def _unresolved_required(row: ModelInventoryRow, baseline: dict[str, Any]) -> tuple[str, ...]:
    runtime_resolved = _RUNTIME_RESOLVED_REQUIRED.get(row.library, set())
    return tuple(
        sorted(
            name
            for name in row.required_args
            if name not in baseline and name not in runtime_resolved
        )
    )


def build_search_spaces(
    rows: list[ModelInventoryRow],
    *,
    train_rows: int,
) -> list[ModelSearchSpace]:
    """Build one explicit search-space status row per canonical identity."""

    output: list[ModelSearchSpace] = []
    for row in rows:
        route_reason = known_route_reason(row)
        if route_reason == "EXPECTED_NEGATIVE_CONTROL":
            output.append(
                _closed_space(
                    row,
                    SearchSpaceStatus.EXPECTED_NEGATIVE_CONTROL,
                    "negative control must not be tuned into a finite forecaster",
                )
            )
            continue
        if route_reason and route_reason.startswith("NON_STANDALONE_METHOD"):
            output.append(_closed_space(row, SearchSpaceStatus.NON_STANDALONE_METHOD, route_reason))
            continue
        if route_reason:
            output.append(_closed_space(row, SearchSpaceStatus.NOT_ROUTABLE, route_reason))
            continue
        if row.supports_bingo5 is False:
            output.append(
                _closed_space(
                    row,
                    SearchSpaceStatus.NOT_ROUTABLE,
                    row.reason_if_not_supported or "not routable for Bingo5",
                )
            )
            continue

        baseline = _baseline_params(row)
        unresolved_required = _unresolved_required(row, baseline)
        if unresolved_required:
            output.append(
                _closed_space(
                    row,
                    SearchSpaceStatus.UNRESOLVED_PARAMETER,
                    "required constructor arguments have no approved runtime/default resolution",
                    unresolved=unresolved_required,
                )
            )
            continue

        tunable = [item for item in row.parameter_inventory if item.tunable]
        dimensions = tuple(
            dimension
            for descriptor in tunable
            if (dimension := _dimension(descriptor.name, train_rows=train_rows)) is not None
        )
        resolved_dimensions = {dimension.parameter for dimension in dimensions}
        unresolved_dimensions = {
            descriptor.name for descriptor in tunable
        }.difference(resolved_dimensions)
        missing_anchors = {
            dimension.parameter for dimension in dimensions if dimension.parameter not in baseline
        }
        unresolved = tuple(sorted(unresolved_dimensions | missing_anchors))
        if unresolved:
            output.append(
                _closed_space(
                    row,
                    SearchSpaceStatus.UNRESOLVED_PARAMETER,
                    (
                        "tunable parameters lack an approved bounded rule or explicit baseline anchor; "
                        "upstream/source review is required before execution"
                    ),
                    unresolved=unresolved,
                )
            )
            continue
        if not dimensions:
            output.append(
                _closed_space(
                    row,
                    SearchSpaceStatus.NO_TUNABLE_PARAMETERS,
                    "no automatically approved accuracy-tunable constructor parameter found",
                )
            )
            continue

        cost_class = "cheap" if row.library == "statsforecast" else "medium"
        budget = 100 if cost_class == "cheap" else 50
        ofat_trials = 1 + sum(
            sum(value != baseline[dimension.parameter] for value in dimension.values)
            for dimension in dimensions
        )
        output.append(
            ModelSearchSpace(
                model_id=row.model_id,
                status=SearchSpaceStatus.READY,
                baseline_params=baseline,
                dimensions=dimensions,
                trial_budget=min(budget, ofat_trials),
                reason="coarse one-factor-at-a-time screening; no Cartesian product is permitted",
            )
        )

    output.sort(key=lambda item: item.model_id)
    if len(output) != len(rows):
        raise AssertionError("search-space generation lost model identities")
    return output
